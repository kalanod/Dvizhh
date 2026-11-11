/** Load a visible prefix using the API's bounded offset/limit pages. */
export async function loadPages<T>(
    load: (offset: number, limit: number) => Promise<T[]>,
    limit = 20,
    offset = 0,
): Promise<T[]> {
    const items: T[] = [];
    while (items.length < limit) {
        const size = Math.min(100, limit - items.length);
        const page = await load(offset + items.length, size);
        items.push(...page);
        if (page.length < size) break;
    }
    return items;
}
