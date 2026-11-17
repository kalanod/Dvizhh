import type { DiscoveryMapItem } from "../api/discovery";

const STATES = {
    default: { classes: "bg-bordermain text-white", label: "Открыто" },
    going: { classes: "bg-pink-600 text-white", label: "Иду" },
    organizer: { classes: "bg-red-600 text-white", label: "Организую" },
    favorite: { classes: "bg-yellow-300 text-textprimary", label: "В избранном" },
};
const plural = new Intl.PluralRules("ru");
const nouns: Record<string, string> = { one: "движ", few: "движа", many: "движей", other: "движей" };

export function mapMarkerPresentation(item: DiscoveryMapItem) {
    const state = STATES[item.state ?? "default"];
    return {
        classes: state.classes,
        tooltip: item.type === "cluster"
            ? `${item.count} ${nouns[plural.select(item.count)]} рядом`
            : `${item.title || "Открыть мероприятие"}\n${state.label}`,
    };
}
