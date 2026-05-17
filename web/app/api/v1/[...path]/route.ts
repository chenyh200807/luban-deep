import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function getApiProxyTarget() {
  const configured =
    process.env.NEXT_API_PROXY_TARGET ||
    process.env.API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_BASE;
  if (configured && configured !== "__CURRENT_ORIGIN__") {
    return configured.replace(/\/$/, "");
  }

  const backendPort = process.env.BACKEND_PORT || "8001";
  return `http://127.0.0.1:${backendPort}`;
}

function buildTargetUrl(request: NextRequest, pathSegments: string[]) {
  const target = new URL(`/api/v1/${pathSegments.map(encodeURIComponent).join("/")}`, getApiProxyTarget());
  target.search = request.nextUrl.search;
  return target;
}

function copyRequestHeaders(request: NextRequest) {
  const headers = new Headers(request.headers);
  for (const header of Array.from(headers.keys())) {
    if (HOP_BY_HOP_HEADERS.has(header.toLowerCase())) {
      headers.delete(header);
    }
  }
  return headers;
}

async function proxy(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const params = await context.params;
  const pathSegments = params.path ?? [];
  const targetUrl = buildTargetUrl(request, pathSegments);
  const method = request.method.toUpperCase();

  try {
    const upstream = await fetch(targetUrl, {
      method,
      headers: copyRequestHeaders(request),
      body: method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer(),
      redirect: "manual",
    });

    const responseHeaders = new Headers(upstream.headers);
    for (const header of Array.from(responseHeaders.keys())) {
      if (HOP_BY_HOP_HEADERS.has(header.toLowerCase())) {
        responseHeaders.delete(header);
      }
    }

    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json({ error: "API backend is unavailable." }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
