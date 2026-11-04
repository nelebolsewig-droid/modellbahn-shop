/** Send the browser to the payment provider's page (its own module, so tests can stand in for it). */
export function openPaymentPage(url: string): void {
  window.location.assign(url);
}
