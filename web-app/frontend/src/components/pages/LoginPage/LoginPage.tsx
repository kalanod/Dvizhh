import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { errorText, getUser } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import { AuthLayout } from "../../layouts";
import { Button, ButtonGhost, FormField, Input, Notice } from "../../ui";

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
            setError("ID профиля — это UUID вида 3f2b…-…; его можно скопировать на странице профиля.");
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
        <AuthLayout title="Вход" subtitle="Найдите, куда пойти сегодня">
            <Notice>
                Авторизация ещё в разработке. Пока вход — по ID профиля: он показан в профиле после
                регистрации.
            </Notice>

            <form className="flex w-full flex-col gap-4" onSubmit={handleSubmit} noValidate>
                <FormField label="ID профиля" htmlFor="user-id" required>
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

                {error && <Notice tone="error">{error}</Notice>}

                <div className="flex w-full items-center justify-between gap-2">
                    <span className="text-body text-textsecondary">Ещё нет профиля?</span>
                    <ButtonGhost text="Зарегистрироваться" onClick={() => navigate(`/register?next=${encodeURIComponent(next)}`)} />
                </div>

                <Button type="submit" state="hover1" disabled={submitting} className="w-full">
                    {submitting ? "Входим…" : "Войти"}
                </Button>
            </form>
        </AuthLayout>
    );
};
