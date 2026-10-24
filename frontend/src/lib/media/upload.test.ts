import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "@/test/render";

import {
  imageTypeOf,
  MAX_IMAGE_BYTES,
  sha256Hex,
  UnsuitableFileError,
  uploadImage,
  type PutFile,
  type UploadProgress,
} from "./upload";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

const ASSET = {
  id: "0199a8c0-0000-7000-8000-0000000000aa",
  kind: "image",
  status: "pending_upload",
  original_filename: "stellwerk.jpg",
  mime_type: "image/jpeg",
  size_bytes: 3,
  failure_code: null,
  created_at: "2026-10-24T10:00:00Z",
  ready_at: null,
  image: null,
  renditions: [],
};

function file(name = "stellwerk.jpg", type = "image/jpeg", content = "abc"): File {
  return new File([content], name, { type });
}

describe("imageTypeOf", () => {
  it("takes the browser's type, or the extension when the browser reports none", () => {
    expect(imageTypeOf({ name: "a.jpg", type: "image/jpeg" })).toBe("image/jpeg");
    expect(imageTypeOf({ name: "IMG_0001.HEIC", type: "" })).toBe("image/heic");
    expect(imageTypeOf({ name: "plan.pdf", type: "application/pdf" })).toBeNull();
    expect(imageTypeOf({ name: "animation.gif", type: "image/gif" })).toBeNull();
    expect(imageTypeOf({ name: "ohne-endung", type: "" })).toBeNull();
  });
});

describe("sha256Hex", () => {
  it("is the lower-case hex digest", async () => {
    expect(await sha256Hex(new Blob(["abc"]))).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });
});

describe("uploadImage", () => {
  it("announces the file, puts it into the storage and completes the upload", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          asset: ASSET,
          upload: {
            url: "https://localhost/mb-media-private/incoming/x/original?X-Amz-Signature=s",
            method: "PUT",
            headers: { "Content-Type": "image/jpeg" },
            expires_at: "2026-10-24T10:15:00Z",
          },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ...ASSET, status: "uploaded" }));
    const put = vi.fn<PutFile>(async (_url, _file, _headers, onProgress) => {
      onProgress(0.5);
      onProgress(1);
    });
    const progress: UploadProgress[] = [];

    const asset = await uploadImage(file(), { put, onProgress: (p) => progress.push(p) });

    expect(asset.status).toBe("uploaded");
    const [ticketUrl, ticketInit] = fetchMock.mock.calls[0] ?? [];
    expect(ticketUrl).toBe("/api/v1/admin/media/uploads");
    expect(JSON.parse(String(ticketInit?.body))).toEqual({
      filename: "stellwerk.jpg",
      mime_type: "image/jpeg",
      size_bytes: 3,
      sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    });
    expect(put).toHaveBeenCalledWith(
      "https://localhost/mb-media-private/incoming/x/original?X-Amz-Signature=s",
      expect.any(File),
      { "Content-Type": "image/jpeg" },
      expect.any(Function),
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/v1/admin/media/${ASSET.id}/complete`);
    expect(progress.map((p) => `${p.phase}:${p.fraction}`)).toEqual([
      "checking:0",
      "uploading:0",
      "uploading:0.5",
      "uploading:1",
      "completing:0",
    ]);
  });

  it("does not send a file the shop already has", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ asset: { ...ASSET, status: "ready" }, upload: null }));
    const put = vi.fn<PutFile>();

    const asset = await uploadImage(file(), { put });

    expect(asset.status).toBe("ready");
    expect(put).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refuses unsuitable files before sending anything", async () => {
    await expect(uploadImage(file("plan.pdf", "application/pdf"))).rejects.toEqual(
      new UnsuitableFileError("type"),
    );
    const huge = file();
    Object.defineProperty(huge, "size", { value: MAX_IMAGE_BYTES + 1 });
    await expect(uploadImage(huge)).rejects.toMatchObject({ reason: "size" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
