import { request } from "./client";
import type { TagCategoryGroup } from "../models/tag";

export const listTags = (signal?: AbortSignal) => request<TagCategoryGroup[]>("/tags", { signal });
