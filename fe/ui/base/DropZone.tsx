"use client";

import { cn } from "@/services/tech/TailwindS";
import * as React from "react";

interface DropZoneProps extends React.ComponentProps<"button"> {
  isDragging?: boolean;
  onFiles: (files: FileList) => void;
  accept?: string;
  multiple?: boolean;
}

function DropZone({
  isDragging = false,
  onFiles,
  accept,
  multiple,
  disabled,
  children,
  className,
  ...props
}: DropZoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
  };

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        data-dragging={isDragging || undefined}
        className={cn(
          "flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          "disabled:pointer-events-none disabled:opacity-50",
          "border-border hover:border-primary/50 hover:bg-muted/40",
          "data-[dragging]:border-primary data-[dragging]:bg-primary/5",
          className
        )}
        {...props}
      >
        {children}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        data-testid="dropzone-file-input"
        onChange={(e) => {
          if (e.target.files) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </>
  );
}

export { DropZone };
