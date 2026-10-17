export async function parseGenerateResponse(response) {
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error("The API returned an unreadable response. Please try again.");
  }

  if (!response.ok) {
    const detail = typeof body?.detail === "string"
      ? body.detail
      : "The request was rejected. Check your description and try again.";
    throw new Error(detail);
  }

  return body;
}
