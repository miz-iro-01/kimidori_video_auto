/**
 * KIMIDORI Movie Auto — Firebase 設定
 * ※ 実際のプロジェクトでは各値を自分のFirebaseプロジェクトの値に置き換えてください
 */

const firebaseConfig = {
  apiKey: "AIzaSyBLOVuFivURHnG7ohomZSLqO5P9vLWdOiI",
  authDomain: "threads-auto-poster-9f85a.firebaseapp.com",
  projectId: "threads-auto-poster-9f85a",
  storageBucket: "threads-auto-poster-9f85a.firebasestorage.app",
  messagingSenderId: "84265380422",
  appId: "1:84265380422:web:2d6fe9e1dc167c9ac9f847",
};

// Firebase初期化
firebase.initializeApp(firebaseConfig);

// サービス参照
const auth = firebase.auth();
const db = firebase.firestore();
const storage = firebase.storage();

// Cloud Run APIのベースURL
// ※ デプロイ後に実際のCloud Run URLに変更してください
const API_BASE_URL = "https://kimidori-movie-auto-84265380422.asia-northeast1.run.app";

console.log("🔥 Firebase 初期化完了");
