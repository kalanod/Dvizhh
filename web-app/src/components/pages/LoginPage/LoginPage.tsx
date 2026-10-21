import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { errorText, getUser } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import { AuthLayout } from "../../layouts";
import { Button, FormField, Input, Notice } from "../../ui";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const LoginPage = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { signIn } = useCurrentUser();
    const [userId, setUserId] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const next = searchParams.get("next") ?? "/";

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const id = userId.trim();
        if (!UUID_RE.test(id)) {
            setError("ID профиля — это UUID; его можно скопировать на странице профиля.");
            return;
        }
        setSubmitting(true);
        setError(null);
        try {
            signIn(await getUser(id));
            navigate(next, { replace: true });
        } catch (err) {
            setError(errorText(err));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <AuthLayout title="Вход">
            <form className="flex w-full flex-col items-start gap-2.5" onSubmit={handleSubmit} noValidate>
                <FormField label="ID профиля" htmlFor="user-id">
                    <Input
                        id="user-id"
                        name="user-id"
                        placeholder="00000000-0000-0000-0000-000000000000"
                        autoComplete="username"
                        value={userId}
                        state={error ? "error" : "default"}
                        onChange={setUserId}
                    />
                </FormField>

                <span className="text-duration text-textsecondary">
                    Авторизация в разработке: пока вход выполняется по ID, который показан в профиле.
                </span>

                {error && <Notice tone="error">{error}</Notice>}

                <div className="flex w-full items-center justify-between">
                    <span className="text-body text-textprimary">Нет профиля?</span>
                    <button
                        type="button"
                        onClick={() => navigate(`/register?next=${encodeURIComponent(next)}`)}
                        className="cursor-pointer text-body text-textghost hover:opacity-80"
                    >
                        Зарегистрироваться
                    </button>
                </div>

                <div className="flex w-full items-center justify-center gap-2.5 py-5">
                    <Button type="submit" state="hover1" disabled={submitting}>
                        {submitting ? "Входим..." : "Войти"}
                    </Button>
                </div>
            </form>
        </AuthLayout>
    );
};
