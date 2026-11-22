import type { PictureImage } from "@/components/ui/responsive-picture";
import type { FairImageOut } from "@/lib/api/generated/model";

/** The photo of a fair as picture data, once its sizes exist. */
export function fairPicture(image: FairImageOut | null | undefined): PictureImage | null {
  if (
    !image ||
    !image.ready ||
    image.renditions.length === 0 ||
    image.width === null ||
    image.height === null ||
    image.lqip === null
  ) {
    return null;
  }
  return {
    width: image.width,
    height: image.height,
    lqip: image.lqip,
    dominant_color: image.dominant_color ?? "#efe7dc",
    renditions: image.renditions,
  };
}

/** Is a photo still being processed by the worker (neither shown nor failed)? */
export function fairImagePending(image: FairImageOut | null | undefined): boolean {
  return !!image && !image.ready && !image.failed;
}
