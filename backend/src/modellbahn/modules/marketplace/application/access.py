"""The access token for eBay's APIs, renewed with the refresh token when it runs out."""

from datetime import timedelta
from typing import Final

import structlog

from modellbahn.modules.marketplace.application.ports import (
    AuthorizationRevokedError,
    EbayGateway,
    TokenCipher,
    UnitOfWorkFactory,
)
from modellbahn.modules.marketplace.domain.errors import NotConnectedError
from modellbahn.platform.clock import Clock

_logger = structlog.get_logger(__name__)

# Renew a little early: a call must not start with a token that runs out on the way.
TOKEN_MARGIN: Final = timedelta(minutes=5)


class EbayAccess:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        gateway: EbayGateway,
        cipher: TokenCipher,
        clock: Clock,
    ) -> None:
        self._uow = uow_factory
        self._gateway = gateway
        self._cipher = cipher
        self._clock = clock

    async def token(self) -> str:
        """A valid access token; :class:`NotConnectedError` if eBay's consent is gone."""
        now = self._clock.now()
        async with self._uow() as uow:
            # The lock keeps two callers from renewing at once.
            account = await uow.account.get(for_update=True)
            if account is None or not account.is_connected:
                raise NotConnectedError
            token = self._cipher.decrypt(account.access_token)
            expires = account.access_expires_at
            if token and expires is not None and expires > now + TOKEN_MARGIN:
                return token
            refresh = self._cipher.decrypt(account.refresh_token)
            try:
                if not refresh:
                    raise AuthorizationRevokedError("no refresh token (another token key?)")
                grant = await self._gateway.refresh(refresh)
            except AuthorizationRevokedError as exc:
                account.expire(now)
                await uow.commit()
                _logger.warning("marketplace.ebay.consent_expired", reason=str(exc))
                raise NotConnectedError from exc
            account.renew(
                access_token=self._cipher.encrypt(grant.access_token),
                access_expires_at=grant.access_expires_at,
                now=now,
            )
            await uow.commit()
            return grant.access_token

    async def rejected(self) -> None:
        """eBay refused the token before it ran out: the next call fetches a new one."""
        now = self._clock.now()
        async with self._uow() as uow:
            account = await uow.account.get(for_update=True)
            if account is not None and account.is_connected:
                account.renew(access_token="", access_expires_at=now, now=now)
                await uow.commit()
