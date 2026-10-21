import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import {
    CalendarPage,
    EventFormPage,
    EventPage,
    FeedPage,
    LoginPage,
    ProfilePage,
    RegistrationPage,
} from "../components/pages";
import { CurrentUserProvider } from "./CurrentUserProvider";

function App() {
    return (
        <CurrentUserProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<FeedPage />} />
                    <Route path="/events/new" element={<EventFormPage />} />
                    <Route path="/events/:id" element={<EventPage />} />
                    <Route path="/events/:id/edit" element={<EventFormPage />} />
                    <Route path="/calendar" element={<CalendarPage />} />
                    <Route path="/profile" element={<ProfilePage />} />
                    <Route path="/users/:id" element={<ProfilePage />} />
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/register" element={<RegistrationPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </BrowserRouter>
        </CurrentUserProvider>
    );
}

export default App;
