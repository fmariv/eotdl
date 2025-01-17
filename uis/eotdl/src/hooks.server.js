import { verifyToken } from "$lib/auth/auth0";
import cookie from "cookie";

export const handle = async ({ event, resolve }) => {
  const cookies = cookie.parse(event.request.headers.get("cookie") || "");
  event.locals.id_token = cookies.id_token;
  if (cookies?.id_token) {
    const user = await verifyToken(cookies.id_token);
    if (!user) {
      console.log("unauthenticated");
      event.locals.user = null;
      event.locals.id_token = null;
      if (event.url.pathname.startsWith("/api")) {
        console.log("unauthenticated server-side api call, returning a 401");
        return {
          status: 401,
          headers: {
            "WWW-Authenticate": "Bearer",
          },
        };
      }
    }
    event.locals.user = user;
  }
  const response = await resolve(event);
  return response;
};

export const getSession = (event) => {
  return {
    user: event.locals.user,
    id_token: event.locals.id_token,
  };
};
