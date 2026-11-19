import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useAuthRedirect } from "../auth/useAuthRedirect";
import AuthCard from "../components/AuthCard";
import AuthSuccess from "../components/AuthSuccess";
import SignInForm from "../components/SignInForm";
import SocialButtons from "../components/SocialButtons";

export default function SignInPage() {
  const { user } = useAuth();
  const { next, finish, from, prefillEmail, justRegistered } = useAuthRedirect();
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  // Redirect only users who were signed in before; a fresh sign in shows the success screen.
  const [signedInOnArrival] = useState(Boolean(user));

  if (done) return <AuthSuccess message="You're signed in." onContinue={finish} />;
  if (signedInOnArrival) return <Navigate to={next} replace />;

  return (
    <AuthCard
      title="Sign in"
      subtitle="Welcome back! Choose how you want to sign in"
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link to="/signup" state={{ from }}>
            Sign up
          </Link>
        </>
      }
    >
      {justRegistered && (
        <p className="notice-success" role="status">
          Account created. Sign in to continue.
        </p>
      )}
      <SignInForm prefillEmail={prefillEmail} focusPassword={justRegistered} onDone={() => setDone(true)} />
      <div className="divider">or</div>
      <SocialButtons onDone={finish} onError={setError} />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </AuthCard>
  );
}
