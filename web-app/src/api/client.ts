type QueryValue = string | number | boolean | null | undefined;

interface RequestOptions {
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    body?: unknown;
    /** Байты файла: уходят как application/octet-stream, а не JSON. */
    file?: Blob;
    query?: Record<string, QueryValue>;
}

export class ApiError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

/** Запрос к backend через прокси web-app: все пути начинаются с /api. */
export async function request<T>(path: string, { method = "GET", body, file, query }: RequestOptions = {}): Promise<T> {
    const url = new URL(`/api${path}`, window.location.origin);
    for (const [key, value] of Object.entries(query ?? {})) {
        if (value !== undefined && value !== null && value !== "" && value !== false) {
            url.searchParams.set(key, String(value));
        }
    }

    let response: Response;
    try {
        response = await fetch(
            url,
            file
                ? { method, headers: { "Content-Type": "application/octet-stream" }, body: file }
                : {
                      method,
                      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
                      body: body === undefined ? undefined : JSON.stringify(body),
                  },
        );
    } catch {
        throw new ApiError("Сервер недоступен. Проверьте подключение.", 0);
    }

    if (response.status === 204) {
        return undefined as T;
    }

    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
        throw new ApiError(errorMessage(payload, response.status), response.status);
    }
    return payload as T;
}

function errorMessage(payload: unknown, status: number): string {
    const detail = (payload as { detail?: unknown } | null)?.detail;

    if (status === 413) {
        return "Файл слишком большой.";
    }
    if (status === 415) {
        return "Формат не поддерживается: подойдут JPEG, PNG или WebP.";
    }

    if (typeof detail === "string") {
        return status === 502 ? "Backend недоступен. Попробуйте позже." : detail;
    }

    // Ошибки валидации FastAPI: [{ loc, msg, type }, ...]
    if (Array.isArray(detail)) {
        const messages = detail
            .map((item: { msg?: unknown; loc?: unknown }) => {
                const msg = typeof item?.msg === "string" ? item.msg.replace(/^Value error, /, "") : "";
                const field = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
                return field && !msg.endsWith(".") ? `${field}: ${msg}` : msg;
            })
            .filter(Boolean);
        if (messages.length > 0) {
            return messages.join("; ");
        }
    }

    return `Ошибка сервера (${status}).`;
}

export const errorText = (error: unknown): string =>
    error instanceof Error ? error.message : "Что-то пошло не так.";
