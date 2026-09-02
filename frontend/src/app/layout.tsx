import type { Metadata } from "next";
import "@xterm/xterm/css/xterm.css";
import "./globals.css";
import Providers from "./providers";
import TitleBar from "../components/TitleBar";
import DesktopAuthBridge from "../components/DesktopAuthBridge";
import DesktopCodeRouteGuard from "../components/DesktopCodeRouteGuard";

export const metadata: Metadata = {
  title: "Arceus Code",
  description: "Proof-first AI engineering workspace for planning, coding, terminal execution, diffs, checks, and pull requests.",
  icons: {
    icon: "/arceus-logo.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <TitleBar />
          <DesktopAuthBridge />
          <DesktopCodeRouteGuard>
            {children}
          </DesktopCodeRouteGuard>
        </Providers>
      </body>
    </html>
  );
}
