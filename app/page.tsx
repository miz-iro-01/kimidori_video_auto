import { redirect } from 'next/navigation';

export default function RootPage() {
  // 既存のKIMIDORI YouTube Autoアプリケーション（frontend/index.html）へ自動リダイレクト
  redirect('/index.html');
}
