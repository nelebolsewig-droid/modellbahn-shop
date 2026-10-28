/*
 * Reading barcodes with the phone's camera. Chrome on Android brings a BarcodeDetector
 * of its own; Safari on the iPhone does not, so there the same interface comes from
 * zxing-wasm (the `barcode-detector` ponyfill), loaded only when needed and from this
 * origin (`/zxing/`, copied there by scripts/copy-zxing-wasm.mjs).
 *
 * The labels carry two symbologies: EAN-13 (the article, for the till) and Code 128
 * (unit and location). Asking for just these keeps the reader fast and stops it from
 * finding codes in the wood grain of a shelf.
 */

export const LABEL_FORMATS = ["ean_13", "code_128"] as const;

const WASM_PATH = "/zxing/zxing_reader.wasm";

export type DetectedCode = { rawValue: string };

export interface CodeDetector {
  detect(source: HTMLVideoElement): Promise<DetectedCode[]>;
}

type NativeDetectorClass = {
  new (options: { formats: string[] }): CodeDetector;
  getSupportedFormats(): Promise<string[]>;
};

function nativeDetectorClass(): NativeDetectorClass | null {
  const candidate = (globalThis as { BarcodeDetector?: NativeDetectorClass }).BarcodeDetector;
  return typeof candidate === "function" ? candidate : null;
}

/** The browser's own detector if it reads both formats, otherwise the WebAssembly one. */
export async function createCodeDetector(): Promise<CodeDetector> {
  const Native = nativeDetectorClass();
  if (Native !== null) {
    try {
      const supported = await Native.getSupportedFormats();
      if (LABEL_FORMATS.every((format) => supported.includes(format))) {
        return new Native({ formats: [...LABEL_FORMATS] });
      }
    } catch {
      // Some browsers expose the class but refuse to use it: fall through.
    }
  }
  const { BarcodeDetector, prepareZXingModule } = await import("barcode-detector/ponyfill");
  prepareZXingModule({
    overrides: {
      locateFile: (path: string, prefix: string) => (path.endsWith(".wasm") ? WASM_PATH : prefix + path),
    },
  });
  return new BarcodeDetector({ formats: [...LABEL_FORMATS] });
}

export type CameraProblem = "denied" | "missing" | "insecure" | "failed";

/** Why the camera could not start, from the error getUserMedia threw. */
export function cameraProblem(error: unknown): CameraProblem {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "denied";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "missing";
  }
  return name === "InsecureContextError" ? "insecure" : "failed";
}

/** The back camera, sharp enough for a 0.29 mm module at a hand's distance. */
export async function openBackCamera(): Promise<MediaStream> {
  if (typeof navigator === "undefined" || navigator.mediaDevices?.getUserMedia === undefined) {
    // Browsers hide the camera on pages served without HTTPS.
    throw new DOMException("Camera API unavailable", "InsecureContextError");
  }
  return navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: "environment" },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
    },
  });
}

/** Whether the camera's lamp can be switched on (most Android phones; not iOS Safari). */
export function supportsTorch(track: MediaStreamTrack | undefined): boolean {
  if (track === undefined || typeof track.getCapabilities !== "function") {
    return false;
  }
  return Boolean((track.getCapabilities() as { torch?: boolean }).torch);
}

export async function setTorch(track: MediaStreamTrack, on: boolean): Promise<void> {
  await track.applyConstraints({ advanced: [{ torch: on } as MediaTrackConstraintSet] });
}
