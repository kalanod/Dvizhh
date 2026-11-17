/** Хештег: буквы любого языка, цифры и подчёркивания; не часть другого слова. */
export const splitHashtags = (title: string) => title.split(/((?<![\p{L}\p{N}_#])#[\p{L}\p{N}_]+)/u);

export const isHashtag = (text: string) => /^#[\p{L}\p{N}_]+$/u.test(text);

export const hashtagSearchUrl = (hashtag: string) => `/?${new URLSearchParams({ q: hashtag })}`;
