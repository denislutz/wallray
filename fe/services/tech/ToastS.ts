import { toast } from "sonner";

// ============================================================================
// Public service API
// ============================================================================

const success = (message: string) => toast.success(message);
const error = (message: string) => toast.error(message);
const info = (message: string) => toast(message);

const ToastS = { success, error, info };
export default ToastS;
