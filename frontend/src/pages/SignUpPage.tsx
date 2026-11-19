import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useAuthRedirect } from "../auth/useAuthRedirect";
import AuthCard from "../components/AuthCard";
import SignUpForm from "../components/SignUpForm";
import SocialButtons from "../components/SocialButtons";

export default function SignUpPage() {
  const { user } = useAuth();
  const { next, finish, from, prefillEmail, prefillName } = useAuthRedirect();
  const [error, setError] = useState("");

  if (user) return <Navigate to={next} replace />;

  return (
    <AuthCard
      title="Create an account"
      subtitle="Sign up with your email or a social account"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" state={{ from }}>
            Sign in
          </Link>
        </>
      }
    >
      <SignUpForm prefillEmail={prefillEmail} prefillName={prefillName} from={from} />
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
