import { HostPage } from "./pages/HostPage";
import { PlayerPage } from "./pages/PlayerPage";

// Two screens, picked by the address:
//   /host  the teacher's projector screen
//   /      everyone else (players on their phones)
export function App() {
  return location.pathname.startsWith("/host") ? <HostPage /> : <PlayerPage />;
}
