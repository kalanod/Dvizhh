import { useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import { useFriendOptions } from "../../../hooks/useFriendOptions";
import { errorText } from "../../../api";
import type { Profile } from "../../../models";
import { Button, Notice } from "../../ui";

const friendLabel = (friend: Profile) => `${friend.display_name} (@${friend.username})`;

export function FriendPicker({ userId, value, disabled, unavailable, onChange }: {
    userId: string; value: Profile | null; disabled: boolean;
    unavailable: (id: string) => string | undefined; onChange: (friend: Profile | null) => void;
}) {
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [inputValue, setInputValue] = useState("");
    const friends = useFriendOptions(userId, query, open && !disabled);
    return <div className="flex min-w-0 flex-1 flex-col gap-2">
        <Autocomplete open={open} onOpen={() => setOpen(true)} onClose={() => setOpen(false)}
            value={value} onChange={(_event, friend) => { onChange(friend); setQuery(""); }}
            inputValue={inputValue} onInputChange={(_event, text, reason) => {
                setInputValue(text);
                if (reason === "input" || reason === "clear") { setQuery(text); onChange(null); }
            }}
            disabled={disabled} options={friends.items} filterOptions={(options) => options}
            getOptionLabel={friendLabel} getOptionKey={(friend) => friend.id}
            isOptionEqualToValue={(option, selected) => option.id === selected.id}
            getOptionDisabled={(friend) => Boolean(unavailable(friend.id))}
            loading={friends.loading} loadingText="Загружаем друзей…"
            noOptionsText={friends.error ? "Не удалось загрузить друзей" : query ? "Друзья не найдены" : "Друзей пока нет"}
            openText="Показать друзей" closeText="Скрыть друзей" clearText="Очистить"
            slotProps={{ paper: { sx: { fontFamily: "var(--font-body)", color: "var(--color-textprimary)" } }, listbox: { style: { maxHeight: 280 }, onScroll: (event) => {
                const list = event.currentTarget;
                if (list.scrollHeight - list.scrollTop - list.clientHeight < 48) friends.loadMore();
            } } }}
            renderOption={({ key, ...props }, friend) => <li key={key} {...props}>
                <span className="flex min-w-0 flex-col">
                    <span className="break-words">{friend.display_name}</span>
                    <span className="text-small text-textsecondary">@{friend.username}{unavailable(friend.id) ? ` · ${unavailable(friend.id)}` : ""}</span>
                </span>
            </li>}
            renderInput={(params) => <TextField {...params} label="Выберите друга" variant="filled"
                slotProps={{ ...params.slotProps, htmlInput: { ...params.slotProps.htmlInput, maxLength: 120 }, input: { ...params.slotProps.input, disableUnderline: true,
                    endAdornment: <>{friends.loading && <CircularProgress size={18} />}{params.slotProps.input.endAdornment}</>,
                } }} />}
            sx={{ fontFamily: "inherit", "& .MuiFilledInput-root": { backgroundColor: "white", borderRadius: "8px", border: `2px solid ${value ? "#25834b" : "var(--color-secondary)"}`, minHeight: 56, fontFamily: "inherit" },
                "& .MuiFilledInput-root:hover, & .MuiFilledInput-root.Mui-focused": { backgroundColor: "white" },
                "& .MuiInputLabel-root": { fontFamily: "inherit", color: "var(--color-textprimary)" } }}
        />
        {friends.error !== undefined && <Notice tone="error">{errorText(friends.error)} <Button onClick={() => { if (!open) setOpen(true); else friends.loadMore(true); }}>Повторить загрузку</Button></Notice>}
    </div>;
}
