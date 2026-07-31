/** 404 fallback. */
import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button, EmptyState } from "@/components/ui";

export function NotFoundPage() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <EmptyState
        icon={<Compass />}
        title="Page not found"
        description="The page you were looking for does not exist."
        action={
          <Link to="/conversations">
            <Button variant="primary" size="sm">
              Go to conversations
            </Button>
          </Link>
        }
      />
    </div>
  );
}

export default NotFoundPage;
