import { cn } from "@/lib/utils";

import { ResponsivePicture, type PictureImage } from "./responsive-picture";

type ModelPhotoProps = {
  image: PictureImage;
  alt: string;
  sizes: string;
  variant?: "full" | "thumb";
  priority?: boolean;
  /** Grows slightly when the surrounding `group` is hovered (catalogue cards). */
  zoom?: boolean;
  className?: string;
};

/**
 * Every model photo in the same frame, whatever the camera delivered: the photo is shown
 * whole and centred, and what its own format leaves empty is filled with a soft blur of
 * the photo itself. A portrait on grey and a landscape on white end up as two frames of
 * the same size, filled to the edge. Fills its parent, which sets format and radius.
 */
export function ModelPhoto({ image, alt, sizes, variant = "full", priority = false, zoom = false, className }: ModelPhotoProps) {
  return (
    <div
      className={cn("absolute inset-0 overflow-hidden rounded-[inherit]", className)}
      style={{ backgroundColor: image.dominant_color }}
    >
      <ResponsivePicture
        image={image}
        alt={alt}
        sizes={sizes}
        variant={variant}
        priority={priority}
        backdrop
        className={cn(zoom && "transition-transform duration-700 ease-settle group-hover:scale-[1.04]")}
      />
      {/* One hairline inside every frame, so light and dark photos end at the same edge. */}
      <span aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-[inherit] shadow-[inset_0_0_0_1px_rgb(30_33_36_/_0.06)]" />
    </div>
  );
}
