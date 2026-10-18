import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createUser, errorText } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import { AuthLayout } from "../../layouts";
import { Button, ButtonGhost, FormField, Input, Notice, Textarea } from "../../ui";

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
        <AuthLayout title="Регистрация" subtitle="Создайте профиль, чтобы ходить на движи и собирать свои">
            <form className="flex w-full flex-col gap-4" onSubmit={handleSubmit} noValidate>
                <FormField
                    label="Никнейм"
                    htmlFor="username"
                    required
                    hint="Строчные латинские буквы, цифры и «_», от 3 символов."
                >
                    <Input
                        id="username"
                        placeholder="dvizh_lover"
                        autoComplete="username"
                        value={formData.username}
                        state={usernameInvalid ? "error" : "default"}
                        onChange={(value) => handleChange("username")(value.toLowerCase())}
                    />
                </FormField>
                <FormField label="Имя" htmlFor="display-name" required>
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
                    <Textarea
                        id="bio"
                        rows={3}
                        maxLength={2000}
                        placeholder="Люблю походы, настолки и джаз"
                        value={formData.bio}
                        onChange={handleChange("bio")}
                    />
                </FormField>

                {error && <Notice tone="error">{error}</Notice>}

                <div className="flex w-full items-center justify-between gap-2">
                    <span className="text-body text-textsecondary">Уже есть профиль?</span>
                    <ButtonGhost text="Войти" onClick={() => navigate("/login")} />
                </div>

                <Button type="submit" state="hover1" disabled={submitting} className="w-full">
                    {submitting ? "Создаём…" : "Зарегистрироваться"}
                </Button>
            </form>
        </AuthLayout>
    );
};
