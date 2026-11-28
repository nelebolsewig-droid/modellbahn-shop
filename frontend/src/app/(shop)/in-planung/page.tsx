import { permanentRedirect } from "next/navigation";

/** "In Planung" is now "Projekte". */
export default function RoadmapMoved() {
  permanentRedirect("/projekte");
}
