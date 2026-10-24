"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export type PictureRendition = {
  name: string;
  format: "webp" | "avif";
  width: number;
  height: number;
  url: string;
};

/** What the media module delivers for a ready image (ImageOut / AdminImageOut). */
export type PictureImage = {
  width: number;
  height: number;
  dominant_color: string;
  lqip: string;
  renditions: readonly PictureRendition[];
};

/** Sizes in the original's aspect ratio; thumb and og are cropped and left out. */
const WIDTH_STEPS: ReadonlySet<string> = new Set(["sm", "md", "lg", "xl"]);

function srcSet(renditions: readonly PictureRendition[], format: "webp" | "avif"): string {
  return renditions
    .filter((r) => r.format === format)
    .map((r) => `${r.url} ${r.width}w`)
    .join(", ");
}

type ResponsivePictureProps = {
  image: PictureImage;
  alt: string;
  /** Layout width for the browser's choice of size, e.g. "(min-width: 1024px) 50vw, 100vw". */
  sizes: string;
  /** "thumb" uses the square 256 px size only (lists, galleries in the admin area). */
  variant?: "full" | "thumb";
  fit?: "contain" | "cover";
  /** Above the fold: load at once instead of lazily. */
  priority?: boolean;
  className?: string;
};

/**
 * A photo from the pre-rendered sizes: AVIF where the browser can, WebP otherwise,
 * each size in the srcset. Until it has loaded, the tiny placeholder (LQIP) shows
 * blurred on the image's dominant colour, then the photo fades in. Fills its parent.
 */
export function ResponsivePicture({
  image,
  alt,
  sizes,
  variant = "full",
  fit = "contain",
  priority = false,
  className,
}: ResponsivePictureProps) {
  const [loaded, setLoaded] = useState(false);
  const ref = useRef<HTMLImageElement>(null);
  const renditions = image.renditions.filter((r) =>
    variant === "thumb" ? r.name === "thumb" : WIDTH_STEPS.has(r.name),
  );
  const fallback =
    renditions.find((r) => r.format === "webp" && r.name === "md") ??
    renditions.findLast((r) => r.format === "webp") ??
    renditions[0];

  useEffect(() => {
    // A cached image may have loaded before React attached onLoad.
    if (ref.current?.complete) {
      setLoaded(true);
    }
  }, []);

  const objectFit = fit === "contain" ? "object-contain" : "object-cover";
  return (
    <div className={cn("relative size-full overflow-hidden", className)}>
      {/* The placeholder only stands in for the photo; screen readers get the photo. */}
      {/* eslint-disable-next-line @next/next/no-img-element -- a data URI, nothing to optimise */}
      <img
        src={image.lqip}
        alt=""
        aria-hidden="true"
        className={cn(
          "absolute inset-0 size-full scale-105 blur-xl transition-opacity duration-300",
          objectFit,
          loaded && "opacity-0",
        )}
      />
      {fallback ? (
        <picture>
          <source type="image/avif" srcSet={srcSet(renditions, "avif")} sizes={sizes} />
          <source type="image/webp" srcSet={srcSet(renditions, "webp")} sizes={sizes} />
          {/* eslint-disable-next-line @next/next/no-img-element -- sizes are pre-rendered */}
          <img
            ref={ref}
            src={fallback.url}
            alt={alt}
            width={fallback.width}
            height={fallback.height}
            loading={priority ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={priority ? "high" : "auto"}
            onLoad={() => setLoaded(true)}
            className={cn(
              "relative size-full transition-opacity duration-300",
              objectFit,
              loaded ? "opacity-100" : "opacity-0",
            )}
          />
        </picture>
      ) : null}
    </div>
  );
}
