import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import { RequireRole, Shell } from "./components/Layout";
import AdminDashboard from "./pages/Admin";
import { Login, Register } from "./pages/Auth";
import DonationDetail from "./pages/DonationDetail";
import { CreateDonation, DonorDashboard } from "./pages/Donor";
import Landing from "./pages/Landing";
import { ImpactDashboard, NotFound, Settings, SystemHealth } from "./pages/Misc";
import NgoDashboard from "./pages/Ngo";
import VolunteerDashboard from "./pages/Volunteer";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/donor" element={<RequireRole roles={["DONOR"]}><DonorDashboard /></RequireRole>} />
            <Route path="/donor/new" element={<RequireRole roles={["DONOR"]}><CreateDonation /></RequireRole>} />
            <Route path="/ngo" element={<RequireRole roles={["NGO"]}><NgoDashboard /></RequireRole>} />
            <Route path="/volunteer" element={<RequireRole roles={["VOLUNTEER"]}><VolunteerDashboard /></RequireRole>} />
            <Route path="/donations/:id" element={<RequireRole><DonationDetail /></RequireRole>} />
            <Route path="/admin" element={<RequireRole roles={["ADMIN"]}><AdminDashboard /></RequireRole>} />
            <Route path="/admin/system" element={<RequireRole roles={["ADMIN"]}><SystemHealth /></RequireRole>} />
            <Route path="/impact" element={<RequireRole><ImpactDashboard /></RequireRole>} />
            <Route path="/settings" element={<RequireRole><Settings /></RequireRole>} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Shell>
      </AuthProvider>
    </BrowserRouter>
  );
}
