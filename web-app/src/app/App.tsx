import { BrowserRouter, Navigate, Outlet, Route, Routes, useMatch } from "react-router-dom";
import {
    CalendarPage,
    EventFormPage,
    EventPage,
    FeedPage,
    LoginPage,
    MyEventsPage,
    NotificationsPage,
    ProfilePage,
    RegistrationPage,
} from "../components/pages";
import { CurrentUserProvider } from "./CurrentUserProvider";
import { AdminPanelPage } from "../components/pages/AdminPanelPage/AdminPanelPage";
import { useEventDiscovery } from "../hooks/useEventDiscovery";

function DiscoveryLayout() {
    const isFeedRoute = useMatch("/") !== null;
    const discovery = useEventDiscovery(isFeedRoute);
    return <Outlet context={discovery} />;
}

function App() {
    return (
        <CurrentUserProvider>
            <BrowserRouter>
                <Routes>
                    <Route element={<DiscoveryLayout />}>
                        <Route index element={<FeedPage />} />
                        <Route path="/admin_panel" element={<AdminPanelPage />} />
                        <Route path="/events/new" element={<EventFormPage />} />
                        <Route path="/events/:id" element={<EventPage />} />
                        <Route path="/events/:id/edit" element={<EventFormPage />} />
                        <Route path="/calendar" element={<CalendarPage />} />
                        <Route path="/my" element={<MyEventsPage />} />
                        <Route path="/notifications" element={<NotificationsPage />} />
                        <Route path="/profile" element={<ProfilePage />} />
                        <Route path="/users/:id" element={<ProfilePage />} />
                    </Route>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/register" element={<RegistrationPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </BrowserRouter>
        </CurrentUserProvider>
    );
}

export default App;
