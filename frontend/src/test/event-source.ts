/** Stands in for the browser's EventSource; the test drives its events. */
export class FakeEventSource extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;

  constructor(readonly url: string) {
    super();
    FakeEventSource.instances.push(this);
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
  }

  open() {
    this.readyState = FakeEventSource.OPEN;
    this.dispatchEvent(new Event("open"));
  }

  emit(type: string, data: unknown) {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(data) }));
  }

  /** `closed`: the browser gives up (e.g. 401); otherwise it retries by itself. */
  fail({ closed }: { closed: boolean }) {
    this.readyState = closed ? FakeEventSource.CLOSED : FakeEventSource.CONNECTING;
    this.dispatchEvent(new Event("error"));
  }
}

export function latestSource(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (source === undefined) {
    throw new Error("no EventSource was opened");
  }
  return source;
}
