"""eBay's REST APIs behind the gateway port: OAuth, Identity, Account, Inventory, Fulfillment.

eBay's model stays in this file (KONZEPT §2.6). The use cases see drafts, published
listings and orders in plain types; what eBay calls an inventory item, an item group,
an offer and a fulfillment is translated here.

A listing is published the way the Inventory API wants it:

* one choice: inventory item, offer, ``publish`` of the offer;
* several choices: an inventory item per variant, the item group with the aspects the
  choices differ in, an offer per variant, ``publish_by_inventory_item_group``.

Rewriting a published listing uses the same calls; eBay updates the live listing.

Failures: no answer, 429 and 5xx raise :class:`MarketplaceUnavailableError` (try again
later); a refused access token :class:`AccessTokenRejectedError`; a refused refresh
token :class:`AuthorizationRevokedError`; everything else eBay refuses
:class:`MarketplaceRejectedError` with eBay's error id and message.
"""

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from urllib.parse import quote, urlencode

import httpx
import structlog

from modellbahn.modules.marketplace.application.ports import (
    AccessGrant,
    AccessTokenRejectedError,
    AuthorizationRevokedError,
    ExternalLine,
    ExternalOrder,
    GatewayMode,
    ListingDraft,
    LocationAddress,
    MarketplaceRejectedError,
    MarketplaceUnavailableError,
    OfferDraft,
    Policies,
    PolicyOption,
    PublishedListing,
    ShipmentReport,
    TokenGrant,
)
from modellbahn.modules.marketplace.domain.model import EBAY_MARKETPLACE

_logger = structlog.get_logger(__name__)

SCOPES: Final = (
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly",
)
CURRENCY: Final = "EUR"
LANGUAGE: Final = "de-DE"
_PAGE_SIZE: Final = 50
_TIMEOUT: Final = httpx.Timeout(20.0, connect=10.0)
# eBay's carrier codes for the names the workshop types when shipping.
_CARRIERS: Final = {
    "DHL": "DHL",
    "DEUTSCHE POST": "DEUTSCHE_POST",
    "POST": "DEUTSCHE_POST",
    "HERMES": "HERMES",
    "DPD": "DPD",
    "GLS": "GLS",
    "UPS": "UPS",
}


@dataclass(frozen=True, slots=True)
class _Hosts:
    api: str
    apiz: str
    auth: str


_HOSTS: Final = {
    GatewayMode.SANDBOX: _Hosts(
        api="https://api.sandbox.ebay.com",
        apiz="https://apiz.sandbox.ebay.com",
        auth="https://auth.sandbox.ebay.com",
    ),
    GatewayMode.PRODUCTION: _Hosts(
        api="https://api.ebay.com",
        apiz="https://apiz.ebay.com",
        auth="https://auth.ebay.com",
    ),
}


def money(cents: int) -> dict[str, str]:
    return {"value": f"{cents // 100}.{cents % 100:02d}", "currency": CURRENCY}


def cents(amount: Mapping[str, Any] | None) -> int:
    if not amount:
        return 0
    return int((Decimal(str(amount.get("value", "0"))) * 100).to_integral_value())


def _timestamp(moment: datetime) -> str:
    return (
        moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
    )


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def carrier_code(carrier: str) -> str:
    """eBay's code for the carrier the workshop named; unknown names go as typed."""
    name = " ".join(carrier.upper().split())
    return _CARRIERS.get(name, name.replace(" ", "_"))


class HttpEbayGateway:
    """eBay's sandbox or production, with the keys of the shop's developer account."""

    def __init__(
        self,
        *,
        mode: GatewayMode,
        client_id: str,
        client_secret: str,
        ru_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if mode is GatewayMode.TEST:
            msg = "the test marketplace is the built-in gateway"
            raise ValueError(msg)
        self._mode = mode
        self._hosts = _HOSTS[mode]
        self._client_id = client_id
        self._client_secret = client_secret
        self._ru_name = ru_name
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT)

    @property
    def mode(self) -> GatewayMode:
        return self._mode

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- OAuth ------------------------------------------------------------------------

    def authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                # eBay names the callback by the RuName of the developer account.
                "redirect_uri": self._ru_name,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "state": state,
                "locale": LANGUAGE,
            },
            quote_via=quote,
        )
        return f"{self._hosts.auth}/oauth2/authorize?{query}"

    async def exchange_code(self, code: str) -> TokenGrant:
        now = datetime.now(UTC)
        body = await self._token(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": self._ru_name}
        )
        return TokenGrant(
            access_token=str(body["access_token"]),
            access_expires_at=now + timedelta(seconds=int(body["expires_in"])),
            refresh_token=str(body["refresh_token"]),
            refresh_expires_at=now + timedelta(seconds=int(body["refresh_token_expires_in"])),
        )

    async def refresh(self, refresh_token: str) -> AccessGrant:
        now = datetime.now(UTC)
        body = await self._token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(SCOPES),
            }
        )
        return AccessGrant(
            access_token=str(body["access_token"]),
            access_expires_at=now + timedelta(seconds=int(body["expires_in"])),
        )

    async def _token(self, form: dict[str, str]) -> dict[str, Any]:
        credentials = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode())
        try:
            response = await self._client.post(
                f"{self._hosts.api}/identity/v1/oauth2/token",
                data=form,
                headers={"Authorization": f"Basic {credentials.decode()}"},
            )
        except httpx.HTTPError as exc:
            raise MarketplaceUnavailableError(str(exc)) from exc
        _raise_if_busy(response)
        body = _json(response)
        if response.is_client_error:
            error = str(body.get("error", "invalid_request"))
            message = str(body.get("error_description", "eBay refused the token request"))
            if form["grant_type"] == "refresh_token" and error == "invalid_grant":
                raise AuthorizationRevokedError(message)
            raise MarketplaceRejectedError(error, message)
        return body

    # --- Seller account ---------------------------------------------------------------

    async def seller_name(self, access_token: str) -> str:
        body = await self._call(
            "GET", f"{self._hosts.apiz}/commerce/identity/v1/user/", access_token
        )
        return str(body.get("username", ""))

    async def policies(self, access_token: str) -> Policies:
        async def options(kind: str, plural: str, id_field: str) -> list[PolicyOption]:
            body = await self._call(
                "GET",
                f"{self._hosts.api}/sell/account/v1/{kind}?marketplace_id={EBAY_MARKETPLACE}",
                access_token,
            )
            return [
                PolicyOption(id=str(policy[id_field]), name=str(policy.get("name", "")))
                for policy in body.get(plural, [])
            ]

        return Policies(
            fulfillment=await options(
                "fulfillment_policy", "fulfillmentPolicies", "fulfillmentPolicyId"
            ),
            payment=await options("payment_policy", "paymentPolicies", "paymentPolicyId"),
            returns=await options("return_policy", "returnPolicies", "returnPolicyId"),
        )

    async def ensure_location(self, access_token: str, key: str, address: LocationAddress) -> None:
        url = f"{self._hosts.api}/sell/inventory/v1/location/{quote(key, safe='')}"
        if await self._call("GET", url, access_token, missing_ok=True):
            return
        await self._call(
            "POST",
            url,
            access_token,
            json={
                "name": address.name,
                "location": {
                    "address": {
                        "addressLine1": address.street,
                        "postalCode": address.postal_code,
                        "city": address.city,
                        "country": address.country_code,
                    }
                },
                "locationTypes": ["WAREHOUSE"],
                "merchantLocationStatus": "ENABLED",
            },
        )

    # --- Listings ---------------------------------------------------------------------

    async def publish(self, access_token: str, draft: ListingDraft) -> PublishedListing:
        group = len(draft.offers) > 1
        was_group = len(draft.previous_skus) > 1
        if draft.previous_external_id and group != was_group:
            # eBay cannot turn a single offer into one with choices or back: the old
            # listing ends, the new one starts.
            await self._end_shape(access_token, draft.group_key, draft.known_offer_ids, was_group)
        for offer in draft.offers:
            await self._put_item(access_token, draft, offer, group=group)
        offer_ids: dict[str, str] = {}
        for offer in draft.offers:
            offer_ids[offer.sku] = await self._put_offer(access_token, draft, offer, group=group)
        if group:
            await self._put_group(access_token, draft)
            body = await self._call(
                "POST",
                f"{self._inventory}/offer/publish_by_inventory_item_group",
                access_token,
                json={"inventoryItemGroupKey": draft.group_key, "marketplaceId": EBAY_MARKETPLACE},
            )
        else:
            body = await self._call(
                "POST",
                f"{self._inventory}/offer/{quote(offer_ids[draft.offers[0].sku], safe='')}/publish",
                access_token,
            )
        listing_id = str(body.get("listingId", ""))
        for sku in set(draft.previous_skus) - {offer.sku for offer in draft.offers}:
            # A choice that is gone (a variant left the shop): its offer goes with it.
            offer_id = draft.known_offer_ids.get(sku)
            if offer_id:
                await self._call(
                    "DELETE",
                    f"{self._inventory}/offer/{quote(offer_id, safe='')}",
                    access_token,
                    missing_ok=True,
                )
        return PublishedListing(external_id=listing_id, offer_ids=offer_ids)

    async def end(self, access_token: str, *, group_key: str, offer_ids: dict[str, str]) -> None:
        await self._end_shape(access_token, group_key, offer_ids, len(offer_ids) > 1)

    async def _end_shape(
        self, access_token: str, group_key: str, offer_ids: Mapping[str, str], group: bool
    ) -> None:
        if group:
            await self._call(
                "POST",
                f"{self._inventory}/offer/withdraw_by_inventory_item_group",
                access_token,
                json={"inventoryItemGroupKey": group_key, "marketplaceId": EBAY_MARKETPLACE},
                missing_ok=True,
            )
            await self._call(
                "DELETE",
                f"{self._inventory}/inventory_item_group/{quote(group_key, safe='')}",
                access_token,
                missing_ok=True,
            )
            return
        for offer_id in offer_ids.values():
            await self._call(
                "POST",
                f"{self._inventory}/offer/{quote(offer_id, safe='')}/withdraw",
                access_token,
                missing_ok=True,
            )

    async def _put_item(
        self, access_token: str, draft: ListingDraft, offer: OfferDraft, *, group: bool
    ) -> None:
        aspects = {**draft.aspects, **offer.aspects}
        product: dict[str, Any] = {
            "title": draft.title,
            "aspects": aspects,
            "imageUrls": list(offer.image_urls or draft.image_urls)[:24],
            # The shop's EAN are its own (for the scanner), not GS1 numbers eBay accepts.
            "ean": ["Nicht zutreffend"],
        }
        if not group:
            product["description"] = draft.description_html
        await self._call(
            "PUT",
            f"{self._inventory}/inventory_item/{quote(offer.sku, safe='')}",
            access_token,
            json={
                "availability": {"shipToLocationAvailability": {"quantity": offer.quantity}},
                "condition": "NEW",
                "product": product,
            },
        )

    async def _put_offer(
        self, access_token: str, draft: ListingDraft, offer: OfferDraft, *, group: bool
    ) -> str:
        body: dict[str, Any] = {
            "sku": offer.sku,
            "marketplaceId": EBAY_MARKETPLACE,
            "format": "FIXED_PRICE",
            "availableQuantity": offer.quantity,
            "categoryId": draft.category_id,
            "merchantLocationKey": draft.location_key,
            "listingPolicies": {
                "fulfillmentPolicyId": draft.fulfillment_policy_id,
                "paymentPolicyId": draft.payment_policy_id,
                "returnPolicyId": draft.return_policy_id,
            },
            "pricingSummary": {"price": money(offer.price_cents)},
        }
        if not group:
            body["listingDescription"] = draft.description_html
        offer_id = draft.known_offer_ids.get(offer.sku) or await self._find_offer(
            access_token, offer.sku
        )
        if offer_id:
            await self._call(
                "PUT",
                f"{self._inventory}/offer/{quote(offer_id, safe='')}",
                access_token,
                json=body,
            )
            return offer_id
        created = await self._call("POST", f"{self._inventory}/offer", access_token, json=body)
        return str(created["offerId"])

    async def _find_offer(self, access_token: str, sku: str) -> str:
        """The offer eBay already has for the SKU (one the shop lost track of), else empty."""
        query = urlencode({"sku": sku, "marketplace_id": EBAY_MARKETPLACE})
        body = await self._call(
            "GET", f"{self._inventory}/offer?{query}", access_token, missing_ok=True
        )
        offers = body.get("offers", [])
        return str(offers[0]["offerId"]) if offers else ""

    async def _put_group(self, access_token: str, draft: ListingDraft) -> None:
        specifications = [
            {
                "name": name,
                "values": list(
                    dict.fromkeys(value for offer in draft.offers for value in offer.aspects[name])
                ),
            }
            for name in draft.varies_by
        ]
        await self._call(
            "PUT",
            f"{self._inventory}/inventory_item_group/{quote(draft.group_key, safe='')}",
            access_token,
            json={
                "title": draft.title,
                "description": draft.description_html,
                "aspects": draft.aspects,
                "imageUrls": list(draft.image_urls)[:24],
                "variantSKUs": [offer.sku for offer in draft.offers],
                "variesBy": {"specifications": specifications},
            },
        )

    # --- Orders -----------------------------------------------------------------------

    async def orders(
        self, access_token: str, *, modified_since: datetime, until: datetime
    ) -> list[ExternalOrder]:
        window = f"lastmodifieddate:[{_timestamp(modified_since)}..{_timestamp(until)}]"
        found: list[ExternalOrder] = []
        offset = 0
        while True:
            query = urlencode({"filter": window, "limit": _PAGE_SIZE, "offset": offset})
            body = await self._call(
                "GET", f"{self._hosts.api}/sell/fulfillment/v1/order?{query}", access_token
            )
            page = body.get("orders", [])
            found.extend(_order(order) for order in page)
            offset += len(page)
            if not page or offset >= int(body.get("total", 0)):
                return found

    async def report_shipment(self, access_token: str, report: ShipmentReport) -> None:
        body: dict[str, Any] = {
            "lineItems": [
                {"lineItemId": line_ref, "quantity": quantity}
                for line_ref, quantity in report.lines
            ],
            "shippedDate": _timestamp(report.shipped_at),
        }
        if report.tracking_number:
            body["shippingCarrierCode"] = carrier_code(report.carrier or "DHL")
            body["trackingNumber"] = report.tracking_number
        await self._call(
            "POST",
            f"{self._hosts.api}/sell/fulfillment/v1/order/"
            f"{quote(report.external_id, safe='')}/shipping_fulfillment",
            access_token,
            json=body,
        )

    # --- Transport --------------------------------------------------------------------

    @property
    def _inventory(self) -> str:
        return f"{self._hosts.api}/sell/inventory/v1"

    async def _call(
        self,
        method: str,
        url: str,
        access_token: str,
        *,
        json: Mapping[str, Any] | None = None,
        missing_ok: bool = False,
    ) -> dict[str, Any]:
        """eBay's answer as JSON (empty if it has none, or if missing and ``missing_ok``)."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Language": LANGUAGE,
            "Accept-Language": LANGUAGE,
        }
        try:
            response = await self._client.request(method, url, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise MarketplaceUnavailableError(str(exc)) from exc
        if response.status_code == httpx.codes.NOT_FOUND and missing_ok:
            return {}
        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise AccessTokenRejectedError("eBay refused the access token")
        _raise_if_busy(response)
        if response.is_client_error:
            code, message = _first_error(_json(response))
            _logger.warning(
                "marketplace.ebay.rejected",
                method=method,
                url=url.split("?", maxsplit=1)[0],
                status=response.status_code,
                code=code,
            )
            raise MarketplaceRejectedError(code, message)
        return _json(response)


def _raise_if_busy(response: httpx.Response) -> None:
    if response.status_code == httpx.codes.TOO_MANY_REQUESTS or response.is_server_error:
        raise MarketplaceUnavailableError(f"eBay answered {response.status_code}")


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _first_error(body: Mapping[str, Any]) -> tuple[str, str]:
    errors: Sequence[Mapping[str, Any]] = body.get("errors") or []
    if not errors:
        return "http_error", "eBay refused the request"
    error = errors[0]
    message = str(error.get("longMessage") or error.get("message") or "")
    return str(error.get("errorId", "unknown")), message


def _order(order: Mapping[str, Any]) -> ExternalOrder:
    """An order of the Fulfillment API in the shop's terms."""
    instructions = order.get("fulfillmentStartInstructions") or [{}]
    ship_to = (instructions[0].get("shippingStep") or {}).get("shipTo") or {}
    address = ship_to.get("contactAddress") or {}
    buyer = order.get("buyer") or {}
    registration = buyer.get("buyerRegistrationAddress") or {}
    street = ", ".join(
        part for part in (address.get("addressLine1"), address.get("addressLine2")) if part
    )
    payments = (order.get("paymentSummary") or {}).get("payments") or []
    paid_at = _parse_time(payments[0].get("paymentDate") if payments else None) or _parse_time(
        order.get("creationDate")
    )
    cancel_state = (order.get("cancelStatus") or {}).get("cancelState", "NONE_REQUESTED")
    lines = []
    for item in order.get("lineItems", []):
        quantity = int(item.get("quantity", 1)) or 1
        lines.append(
            ExternalLine(
                line_ref=str(item["lineItemId"]),
                sku=str(item.get("sku", "")),
                title=str(item.get("title", "")),
                quantity=quantity,
                # lineItemCost is the price of all pieces of the line, before discounts.
                unit_price_cents=cents(item.get("lineItemCost")) // quantity,
            )
        )
    return ExternalOrder(
        external_id=str(order["orderId"]),
        buyer_name=str(buyer.get("username", "")),
        email=str(ship_to.get("email") or registration.get("email") or ""),
        recipient=str(ship_to.get("fullName", "")),
        street=street,
        postal_code=str(address.get("postalCode", "")),
        city=str(address.get("city", "")),
        country_code=str(address.get("countryCode", "")),
        shipping_cents=cents((order.get("pricingSummary") or {}).get("deliveryCost")),
        paid=order.get("orderPaymentStatus") == "PAID",
        cancelled=cancel_state == "CANCELED",
        paid_at=paid_at,
        lines=lines,
    )
