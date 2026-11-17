import { changePassword } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/forms";

export function ChangePasswordForm({ submitLabel = "Change password", continueTo }: { submitLabel?: string; continueTo?: string }) {
  return (
    <ActionForm action={changePassword} className="stack" hidden={continueTo ? { continue_to: continueTo } : undefined}>
      <label>
        Current password
        <input type="password" name="current_password" required autoComplete="current-password" />
      </label>
      <label>
        New password
        <input type="password" name="new_password" required minLength={12} autoComplete="new-password" />
      </label>
      <label>
        Confirm new password
        <input type="password" name="confirm_password" required minLength={12} autoComplete="new-password" />
      </label>
      <p className="small muted">At least 12 characters. A short phrase of unrelated words works well.</p>
      <div><SubmitButton>{submitLabel}</SubmitButton></div>
    </ActionForm>
  );
}
