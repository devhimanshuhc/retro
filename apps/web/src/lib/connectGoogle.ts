"use client";

import { createGoogleSession } from "./api";

/** Sends the browser to Google's sign-in (it asks which account every time). Google returns to the API, which
 * sends the browser back to `returnTo` with `?google=connected`, or to /connectors with `?google_error=…`. */
export async function connectGoogle(returnTo = window.location.pathname): Promise<void> {
  const { url } = await createGoogleSession(returnTo);
  window.location.assign(url);
}
