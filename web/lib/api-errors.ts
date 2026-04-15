export class ApiError extends Error {
  status: number;

  constructor(status: number, message?: string) {
    super(message || `Request failed: ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isAuthUnavailableError(error: unknown): error is ApiError {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}
