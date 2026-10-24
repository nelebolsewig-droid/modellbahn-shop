import type { PictureImage } from "@/components/ui/responsive-picture";
import type { AdminImageOut } from "@/lib/api/generated/model";

/** An image of the admin API as picture data, once it is ready (before, facts are missing). */
export function readyPicture(image: AdminImageOut | null | undefined): PictureImage | null {
  if (
    !image ||
    image.status !== "ready" ||
    image.width === null ||
    image.height === null ||
    image.lqip === null ||
    image.dominant_color === null
  ) {
    return null;
  }
  return {
    width: image.width,
    height: image.height,
    lqip: image.lqip,
    dominant_color: image.dominant_color,
    renditions: image.renditions,
  };
}
