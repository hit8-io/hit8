/**
 * OPTIONS: 200 + CORS. Other methods: forward to origin and add CORS to every response
 * so 5xx/530 from origin or edge still have CORS and the browser shows the real status.
 */
const ALLOWED_ORIGINS = [
  "https://iter8.hit8.io",
  "https://www.hit8.io",
  "https://hit8.io",
];

function corsHeaders(origin) {
  const allowOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, X-Source-Token, X-Org, X-Project",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400",
  };
}

function mergeCorsIntoResponse(response, origin) {
  const h = new Headers(response.headers);
  for (const [k, v] of Object.entries(corsHeaders(origin))) h.set(k, v);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: h,
  });
}

addEventListener("fetch", (event) => {
  const origin = event.request.headers.get("Origin") || "";
  if (event.request.method === "OPTIONS") {
    return event.respondWith(
      new Response(null, { status: 200, headers: corsHeaders(origin) })
    );
  }
  event.respondWith(
    fetch(event.request)
      .then((res) => mergeCorsIntoResponse(res, origin))
      .catch(() =>
        new Response(
          JSON.stringify({ detail: "Origin unreachable" }),
          { status: 503, headers: { "Content-Type": "application/json", ...corsHeaders(origin) } }
        )
      )
  );
});
