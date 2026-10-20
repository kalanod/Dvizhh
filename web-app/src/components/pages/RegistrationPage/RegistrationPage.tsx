import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createUser, errorText } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import { AuthLayout } from "../../layouts";
import { Button, FormField, Input, Notice, Textarea } from "../../ui";

const USERNAME_RE = /^[a-z0-9_]{3,50}$/;

export const RegistrationPage = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { signIn } = useCurrentUser();
    const [formData, setFormData] = useState({ username: "", displayName: "", city: "", bio: "" });
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const next = searchParams.get("next");
    const usernameInvalid = formData.username !== "" && !USERNAME_RE.test(formData.username);

    const handleChange = (field: keyof typeof formData) => (value: string) =>
        setFormData((prev) => ({ ...prev, [field]: value }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!USERNAME_RE.test(formData.username) || !formData.displayName.trim()) {
            setError("Заполните никнейм и имя.");
            return;
        }
        setSubmitting(true);
        setError(null);
        try {
            const profile = await createUser({
                username: formData.username,
                display_name: formData.displayName.trim(),
                city: formData.city.trim() || null,
                bio: formData.bio.trim() || null,
            });
            signIn(profile);
            navigate(next && next !== "/" ? next : "/profile", { replace: true });
        } catch (err) {
            setError(errorText(err));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <AuthLayout title="Регистрация">
            <form className="flex w-full flex-col items-start gap-2.5" onSubmit={handleSubmit} noValidate>
                <FormField label="Никнейм" htmlFor="username" hint="Строчные латинские буквы, цифры и «_», от 3 символов">
                    <Input
                        id="username"
                        placeholder="example"
                        autoComplete="username"
                        value={formData.username}
                        state={usernameInvalid ? "error" : "default"}
                        onChange={(value) => handleChange("username")(value.toLowerCase())}
                    />
                </FormField>
                <FormField label="Имя" htmlFor="display-name">
                    <Input
                        id="display-name"
                        placeholder="Как вас называть"
                        autoComplete="name"
                        maxLength={120}
                        value={formData.displayName}
                        onChange={handleChange("displayName")}
                    />
                </FormField>
                <FormField label="Город" htmlFor="city">
                    <Input
                        id="city"
                        placeholder="Санкт-Петербург"
                        autoComplete="address-level2"
                        maxLength={120}
                        value={formData.city}
                        onChange={handleChange("city")}
                    />
                </FormField>
                <FormField label="О себе" htmlFor="bio">
                    <Textarea id="bio" rows={3} maxLength={2000} value={formData.bio} onChange={handleChange("bio")} />
                </FormField>

                {error && <Notice tone="error">{error}</Notice>}

                <div className="flex w-full items-center justify-center gap-px">
                    <p className="flex-1 text-body text-textprimary">Уже есть аккаунт?</p>
                    <button
                        type="button"
                        onClick={() => navigate("/login")}
                        className="cursor-pointer text-body text-textghost hover:opacity-80"
                    >
                        Войти
                    </button>
                </div>

                <div className="flex w-full items-center justify-center gap-2.5 py-5">
                    <Button type="submit" state="hover1" disabled={submitting}>
                        {submitting ? "Создаём..." : "Зарегистрироваться"}
                    </Button>
                </div>
            </form>
        </AuthLayout>
    );
};
