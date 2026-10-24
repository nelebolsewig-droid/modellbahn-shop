import { completeMediaUpload, requestMediaUpload } from "@/lib/api/generated/admin-media/admin-media";
import type { AssetOut } from "@/lib/api/generated/model";

/*
 * The browser's part of the media pipeline (docs/KONZEPT.md §6, steps 1 to 3): the
 * SHA-256 of the file, the upload ticket, the upload straight into the object
 * storage with the signed URL, and the completion that hands the file to the worker.
 * The file never passes through the API.
 */

export const ACCEPTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/avif",
  "image/heic",
  "image/heif",
] as const;

/** For the file picker: the types plus the extensions some systems report without a type. */
export const IMAGE_PICKER_ACCEPT = [...ACCEPTED_IMAGE_TYPES, ".heic", ".heif"].join(",");

/** The API's limit (IMAGE_MAX_BYTES in the media module). */
export const MAX_IMAGE_BYTES = 50 * 1024 * 1024;

export type UploadPhase = "checking" | "uploading" | "completing";

export type UploadProgress = {
  phase: UploadPhase;
  /** 0 to 1 while uploading; 0 in the other phases. */
  fraction: number;
};

/** A file the shop does not take, found out before anything is sent. */
export class UnsuitableFileError extends Error {
  override readonly name = "UnsuitableFileError";

  constructor(readonly reason: "type" | "size") {
    super(reason === "type" ? "unsupported file type" : "file too large");
  }
}

/** The upload into the storage failed (network, expired URL, refused signature). */
export class StorageUploadError extends Error {
  override readonly name = "StorageUploadError";

  constructor(readonly status: number) {
    super(`storage answered ${status}`);
  }
}

const EXTENSION_TYPES: Readonly<Record<string, string>> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  avif: "image/avif",
  heic: "image/heic",
  heif: "image/heif",
};

/**
 * The type to announce: what the browser reports, or what the extension says when it
 * reports nothing (several systems do so for HEIC photos from iPhones).
 */
export function imageTypeOf(file: Pick<File, "name" | "type">): string | null {
  if ((ACCEPTED_IMAGE_TYPES as readonly string[]).includes(file.type)) {
    return file.type;
  }
  if (file.type !== "") {
    return null;
  }
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return EXTENSION_TYPES[extension] ?? null;
}

/** Lower-case hex SHA-256 of the file, computed with Web Crypto. */
export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export type PutFile = (
  url: string,
  file: Blob,
  headers: Readonly<Record<string, string>>,
  onProgress: (fraction: number) => void,
) => Promise<void>;

/**
 * PUT with upload progress. fetch() cannot report the progress of a request body, so
 * this one uses XMLHttpRequest. Content-Length comes from the file: it is part of the
 * signature, like the Content-Type set here.
 */
export const putWithProgress: PutFile = (url, file, headers, onProgress) =>
  new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    for (const [name, value] of Object.entries(headers)) {
      request.setRequestHeader(name, value);
    }
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(event.loaded / event.total);
      }
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(1);
        resolve();
      } else {
        reject(new StorageUploadError(request.status));
      }
    });
    request.addEventListener("error", () => reject(new StorageUploadError(0)));
    request.addEventListener("abort", () => reject(new StorageUploadError(0)));
    request.send(file);
  });

type UploadOptions = {
  onProgress?: (progress: UploadProgress) => void;
  /** Replaced in tests; the real one is putWithProgress. */
  put?: PutFile;
};

/**
 * Uploads an image and returns its asset, which the worker then processes
 * (`media.asset.ready` arrives on the event stream). A file the shop already has
 * is recognised by its checksum and not sent again.
 */
export async function uploadImage(file: File, options: UploadOptions = {}): Promise<AssetOut> {
  const { onProgress = () => undefined, put = putWithProgress } = options;
  const mimeType = imageTypeOf(file);
  if (mimeType === null) {
    throw new UnsuitableFileError("type");
  }
  if (file.size > MAX_IMAGE_BYTES) {
    throw new UnsuitableFileError("size");
  }

  onProgress({ phase: "checking", fraction: 0 });
  const ticket = await requestMediaUpload({
    filename: file.name,
    mime_type: mimeType,
    size_bytes: file.size,
    sha256: await sha256Hex(file),
  });
  if (ticket.upload === null) {
    return ticket.asset;
  }

  onProgress({ phase: "uploading", fraction: 0 });
  await put(ticket.upload.url, file, ticket.upload.headers, (fraction) =>
    onProgress({ phase: "uploading", fraction }),
  );
  onProgress({ phase: "completing", fraction: 0 });
  return completeMediaUpload(ticket.asset.id);
}
