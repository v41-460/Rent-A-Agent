// Plain-English messages for when Plaid Link closes without connecting.

type LinkError = { error_code?: string; error_type?: string } | null;

export function linkExitMessage(error: LinkError): string {
  if (!error) {
    return "No problem. Nothing was connected. You can try again whenever you're ready.";
  }
  switch (error.error_code) {
    case "INVALID_LINK_TOKEN":
      return "That took a little too long and timed out. Let's try again.";
    case "INSTITUTION_DOWN":
    case "INSTITUTION_NOT_RESPONDING":
    case "INSTITUTION_NOT_AVAILABLE":
      return "Your bank isn't responding right now. This is usually temporary. Please try again in a little while.";
    case "ITEM_LOGIN_REQUIRED":
    case "INVALID_CREDENTIALS":
      return "Your bank didn't accept that sign-in. You can try again; nothing has changed in your account.";
    default:
      return "That didn't work, but nothing has changed in your bank account. Let's try again.";
  }
}
