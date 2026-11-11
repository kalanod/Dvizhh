import type { Coordinates } from "./yandexMaps";

export function currentCoordinates(): Promise<Coordinates> {
    if (window.isSecureContext === false) {
        return Promise.reject(new Error("Для определения местоположения откройте сайт через HTTPS или localhost."));
    }
    if (!navigator.geolocation) {
        return Promise.reject(new Error("Браузер не поддерживает определение местоположения."));
    }
    return new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
            ({ coords }) => resolve([coords.longitude, coords.latitude]),
            (error) => {
                const messages: Record<number, string> = {
                    1: "Доступ к местоположению запрещён. Разрешите его в настройках сайта браузера и попробуйте снова.",
                    2: "Не удалось определить местоположение. Попробуйте ещё раз или выберите точку на карте.",
                    3: "Определение местоположения заняло слишком много времени. Попробуйте снова.",
                };
                reject(new Error(messages[error.code] ?? "Не удалось определить местоположение."));
            },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
        );
    });
}
