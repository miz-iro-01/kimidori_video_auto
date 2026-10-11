import type { Metadata } from 'next';
import React from 'react';

export const metadata: Metadata = {
  title: 'KIMIDORI AI Movie Auto - Pro Studio',
  description: '完全無料AI動画生成 (ComfyUI + LTX-Video) スタジオ',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body style={{ margin: 0, padding: 0, fontFamily: 'system-ui, sans-serif', backgroundColor: '#0f172a', color: '#f8fafc' }}>
        {children}
      </body>
    </html>
  );
}
