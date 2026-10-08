"use client";

import UISessionS from "@/services/business/UISessionS";
import EnvS from "@/services/tech/EnvS";
import UidS from "@/services/tech/UidS";
import { Col } from "@/ui/base/Col";
import { DropZone } from "@/ui/base/DropZone";
import { Row } from "@/ui/base/Row";
import { Text } from "@/ui/base/Text";
import { Thumbnail } from "@/ui/base/Thumbnail";
import { Badge } from "@/ui/base/badge";
import { Button } from "@/ui/base/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/ui/base/card";
import { Progress } from "@/ui/base/progress";
import { AlertCircle, ImagePlus, X } from "lucide-react";
import * as React from "react";
import type { ReactNode } from "react";

// ============================================================================
// Private
// ============================================================================

const MAX_FILES = EnvS.photoMaxCount();
const MIN_FILES = EnvS.photoMinCount();
const MAX_SIZE_MB = EnvS.photoMaxSizeMb();
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic"];

interface UploadedPhoto {
  id: string;
  file: File;
  previewUrl: string;
  error?: string;
}

type T = ReturnType<typeof UISessionS.useT>;

function validateFile(t: T, file: File): string | undefined {
  if (!ACCEPTED_TYPES.includes(file.type)) return t("validate_unsupported_format");
  if (file.size > MAX_SIZE_MB * 1024 * 1024)
    return t("validate_file_too_large", { size: MAX_SIZE_MB.toString() });
}

function FileRow({
  photo,
  onRemove,
  t,
}: {
  photo: UploadedPhoto;
  onRemove: () => void;
  t: T;
}) {
  return (
    <Row gap="sm" py="sm">
      <Thumbnail src={photo.previewUrl} alt={photo.file.name} size="md" />
      <Col gap="none" grow>
        <Text size="sm" weight="medium" truncate>
          {photo.file.name}
        </Text>
        {photo.error ? (
          <Row gap="xs" color="destructive">
            <AlertCircle className="size-3" />
            <Text size="xs">{photo.error}</Text>
          </Row>
        ) : (
          <Text size="xs" color="muted">
            {(photo.file.size / (1024 * 1024)).toFixed(1)} MB
          </Text>
        )}
      </Col>
      <Badge variant={photo.error ? "destructive" : "secondary"}>
        {photo.error ? t("photo_error") : t("photo_ready")}
      </Badge>
      <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label={t("photo_remove_aria")}>
        <X />
      </Button>
    </Row>
  );
}

// ============================================================================
// Public
// ============================================================================

interface PhotoUploadProps {
  onSubmit: (files: File[]) => void;
  isSubmitting?: boolean;
  uploadProgress?: number;
  // Rendered just left of the submit button — e.g. a de-emphasized settings control that
  // belongs next to the submit action but isn't important enough for its own section.
  beforeSubmit?: ReactNode;
}

export function PhotoUpload({
  onSubmit,
  isSubmitting = false,
  uploadProgress,
  beforeSubmit,
}: PhotoUploadProps) {
  const t = UISessionS.useT();
  const [photos, setPhotos] = React.useState<UploadedPhoto[]>([]);
  const [isDragging, setIsDragging] = React.useState(false);

  const addFiles = React.useCallback(
    (incoming: FileList) => {
      const files = Array.from(incoming).slice(0, MAX_FILES - photos.length);
      const next: UploadedPhoto[] = files.map((file) => ({
        id: UidS.randomId(),
        file,
        previewUrl: URL.createObjectURL(file),
        error: validateFile(t, file),
      }));
      setPhotos((prev) => [...prev, ...next]);
    },
    [photos.length, t]
  );

  const removePhoto = React.useCallback((id: string) => {
    setPhotos((prev) => {
      const removed = prev.find((p) => p.id === id);
      if (removed) URL.revokeObjectURL(removed.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
  }, []);

  const validPhotos = photos.filter((p) => !p.error);
  const canSubmit = validPhotos.length >= MIN_FILES && !isSubmitting;

  return (
    <Card width="md">
      <CardHeader>
        <CardTitle>{t("upload_title")}</CardTitle>
        <CardDescription>
          {t("upload_subtitle", {
            min: MIN_FILES.toString(),
            max: MAX_FILES.toString(),
            size: MAX_SIZE_MB.toString(),
          })}
        </CardDescription>
      </CardHeader>

      <CardContent>
        <Col gap="md">
          <DropZone
            isDragging={isDragging}
            onFiles={addFiles}
            accept={ACCEPTED_TYPES.join(",")}
            multiple
            disabled={photos.length >= MAX_FILES || isSubmitting}
            onDragEnter={() => setIsDragging(true)}
            onDragLeave={() => setIsDragging(false)}
            onDrop={() => setIsDragging(false)}
          >
            <ImagePlus className="size-8 text-muted-foreground" />
            <Col gap="none" align="center">
              <Text size="sm" weight="medium">
                {t("dropzone_prompt")}
              </Text>
              <Text size="xs" color="muted">
                {t("dropzone_counter", {
                  count: photos.length.toString(),
                  max: MAX_FILES.toString(),
                })}
              </Text>
            </Col>
          </DropZone>

          {photos.length > 0 && (
            <Col divided gap="none">
              {photos.map((photo) => (
                <FileRow
                  key={photo.id}
                  photo={photo}
                  onRemove={() => removePhoto(photo.id)}
                  t={t}
                />
              ))}
            </Col>
          )}

          {isSubmitting && uploadProgress !== undefined && (
            <Progress value={uploadProgress}>
              <Row grow justify="between">
                <Text size="sm" weight="medium">
                  {t("photo_uploading")}
                </Text>
                <Text size="sm" color="muted" mono>
                  {uploadProgress}%
                </Text>
              </Row>
            </Progress>
          )}
        </Col>
      </CardContent>

      <CardFooter justify="between">
        <Text size="xs" color="muted">
          {validPhotos.length < MIN_FILES
            ? t("photo_need_more", { n: (MIN_FILES - validPhotos.length).toString() })
            : validPhotos.length === 1
              ? t("photos_ready_one", { count: validPhotos.length.toString() })
              : t("photos_ready_many", { count: validPhotos.length.toString() })}
        </Text>
        <Row gap="sm" align="center">
          {beforeSubmit}
          <Button
            onClick={() => canSubmit && onSubmit(validPhotos.map((p) => p.file))}
            disabled={!canSubmit}
          >
            {isSubmitting ? t("action_uploading") : t("action_start_assessment")}
          </Button>
        </Row>
      </CardFooter>
    </Card>
  );
}
