/**
 * KIMIDORI Movie Auto — Firebase 設定
 * ※ 実際のプロジェクトでは各値を自分のFirebaseプロジェクトの値に置き換えてください
 */

const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "your-project.firebaseapp.com",
  projectId: "your-project-id",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abcdef123456",
};

// Firebase初期化
firebase.initializeApp(firebaseConfig);

// サービス参照
const auth = firebase.auth();
const db = firebase.firestore();
const storage = firebase.storage();

// Cloud Run APIのベースURL
// ※ デプロイ後に実際のCloud Run URLに変更してください
const API_BASE_URL = "http://localhost:8080";

console.log("🔥 Firebase 初期化完了");
