import "./globals.css";

export const metadata = {
  title: "AI Ticket Analyzer",
  description: "Chat with product context, preview ticket drafts, and confirm before Jira creation.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}