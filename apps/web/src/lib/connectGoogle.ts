"use client";

import { createGoogleSession, NANGO_CONNECT_URL, NANGO_HOST } from "./api";

/** Opens Nango's Connect UI to sign in to Google. Resolves true once connected, false if the window was closed.
 * The session asks Google for the account chooser every time, so the user picks which account to connect. */
export async function connectGoogle(): Promise<boolean> {
  const { token } = await createGoogleSession();
  const { default: Nango } = await import("@nangohq/frontend");
  return new Promise((resolve) => {
    let done = false;
    new Nango({ connectSessionToken: token, host: NANGO_HOST }).openConnectUI({
      baseURL: NANGO_CONNECT_URL,
      apiURL: NANGO_HOST,
      onEvent: (ev) => {
        if (ev.type === "connect") {
          done = true;
          resolve(true);
        } else if (ev.type === "close" && !done) {
          resolve(false);
        }
      },
    });
  });
}
