// The browser's navigation around the provider's page, in its own module so tests can stand in for it.

/** Send the browser to the payment provider's page. */
export function openPaymentPage(url: string): void {
  window.location.assign(url);
}

/** Load the payment page afresh (after the browser restored it from its cache). */
export function reloadPaymentPage(): void {
  window.location.reload();
}
