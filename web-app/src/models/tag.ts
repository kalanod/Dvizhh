export interface TagCategory {
    id: string;
    name: string;
    color: string;
    sort_order: number;
}

export interface CatalogTag {
    id: string;
    slug: string;
    name: string;
    is_active: boolean;
    category_id: string;
    sort_order: number;
}

export interface TagCategoryGroup extends TagCategory {
    tags: CatalogTag[];
}

export interface EventTag {
    id: string;
    slug: string;
    name: string;
    is_active: boolean;
    category: TagCategory;
}
