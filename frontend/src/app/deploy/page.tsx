import { redirect } from 'next/navigation';

export default function DeployPage() {
  redirect('/workspace?agent=deploy');
}
