import path from "node:path";

// Real, tiny, valid JPEGs — be/app/application/upload_job.py checks magic bytes and opens the
// file with PIL, so a garbage buffer won't pass upload validation.
export const CLOSE_UP_PHOTO = path.resolve(__dirname, "photos/close-up.jpg");
export const CONTEXT_PHOTO = path.resolve(__dirname, "photos/context.jpg");
export const REPORT_PHOTOS = [CLOSE_UP_PHOTO, CONTEXT_PHOTO];
