import { cn } from "@/services/tech/TailwindS";
import { type VariantProps, cva } from "class-variance-authority";

const thumbnailVariants = cva("shrink-0 object-cover", {
  variants: {
    size: {
      sm: "size-8",
      md: "size-10",
      lg: "size-14",
    },
    shape: {
      rounded: "rounded-md",
      circle: "rounded-full",
    },
  },
  defaultVariants: {
    size: "md",
    shape: "rounded",
  },
});

interface ThumbnailProps extends VariantProps<typeof thumbnailVariants> {
  src?: string;
  alt: string;
  className?: string;
  width?: number;
  height?: number;
}

function Thumbnail({ src, alt, size, shape, width, height, className }: ThumbnailProps) {
  if (!src) {
    return (
      <div
        data-slot="thumbnail"
        aria-label={alt}
        className={cn(thumbnailVariants({ size, shape }), "bg-muted", className)}
      />
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      data-slot="thumbnail"
      className={cn(thumbnailVariants({ size, shape }), className)}
    />
  );
}

export { Thumbnail };
