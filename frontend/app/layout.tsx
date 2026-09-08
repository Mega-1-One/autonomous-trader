import "./globals.css";
import React from "react";
import Link from "next/link";

export const metadata = {
  title: "Autonomous Trader Dashboard",
  description: "MT5 Autonomous Quantitative Trading Engine Control Panel",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-textPrimary min-h-screen flex flex-col antialiased">
        <header className="border-b border-border bg-surface px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-6">
            <div className="flex items-center space-x-3">
              <div className="h-3 w-3 rounded-full bg-success animate-pulse" />
              <Link href="/" className="text-xl font-bold tracking-tight hover:text-primary transition-colors">
                AUTONOMOUS TRADER
              </Link>
            </div>
            
            <nav className="hidden md:flex items-center space-x-4 text-sm font-medium text-textSecondary">
              <Link href="/" className="hover:text-textPrimary transition-colors">Overview</Link>
              <Link href="/strategy" className="hover:text-textPrimary transition-colors">Strategy Monitor</Link>
              <Link href="/risk" className="hover:text-textPrimary transition-colors">Risk Engine</Link>
              <Link href="/positions" className="hover:text-textPrimary transition-colors">Positions</Link>
              <Link href="/orders" className="hover:text-textPrimary transition-colors">Signal Log</Link>
              <Link href="/backtest" className="hover:text-textPrimary transition-colors">Backtest & MC</Link>
            </nav>
          </div>

          <div className="flex items-center space-x-4 text-sm font-medium">
            <span className="px-3 py-1 bg-surface border border-border rounded-full text-xs font-semibold text-textSecondary">
              PAPER MODE
            </span>
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </body>
    </html>
  );
}
