import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { errorText, getUser, loginAccount, getAccount } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import { AuthLayout } from "../../layouts";
import { Button, FormField, Input, Notice } from "../../ui";

export const LoginPage = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { signIn } = useCurrentUser();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const next = searchParams.get("next") ?? "/";

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        setError(null);
        try {
            await loginAccount({ email: email.trim(), password });
            const account = await getAccount();
            signIn(await getUser(account.id));
            navigate(next, { replace: true });
        } catch (err) {
            setError(errorText(err));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <AuthLayout title="Вход">
            <form className="flex w-full flex-col items-start gap-2.5" onSubmit={handleSubmit}>
                <FormField label="Email" htmlFor="email">
                    <Input id="email" name="email" type="email" autoComplete="username"
                        placeholder="you@example.com" required maxLength={254} value={email} onChange={setEmail} />
                </FormField>
                <FormField label="Пароль" htmlFor="password">
                    <Input id="password" name="password" type="password" autoComplete="current-password"
                        required maxLength={128} value={password} onChange={setPassword} />
                </FormField>

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
