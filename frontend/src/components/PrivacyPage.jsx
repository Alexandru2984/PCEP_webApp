import { useEffect } from 'react'
import { AnalyticsPreferences } from './AnalyticsConsent'

const CONTACT = 'alex_mihai984@yahoo.com'

export default function PrivacyPage() {
  useEffect(() => {
    const previousTitle = document.title
    document.title = 'Privacy & data — PCEP Quiz'
    return () => {
      document.title = previousTitle
    }
  }, [])

  return (
    <main id="privacy-main" tabIndex={-1} className="mx-auto min-w-0 max-w-3xl">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-8 dark:border-slate-700 dark:bg-slate-900">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50">
          Privacy &amp; data
        </h1>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Last updated: 13 October 2026
        </p>

        <section className="mt-7 space-y-3" aria-labelledby="controller-heading">
          <h2 id="controller-heading" className="text-xl font-semibold">
            Who is responsible
          </h2>
          <p>
            The data controller for PCEP Quiz is Dragne Alexandru Mihai. For privacy
            questions or requests, email{' '}
            <a className="underline" href={`mailto:${CONTACT}`}>
              {CONTACT}
            </a>
            .
          </p>
        </section>

        <section className="mt-7 space-y-3" aria-labelledby="local-heading">
          <h2 id="local-heading" className="text-xl font-semibold">
            Data kept on your device
          </h2>
          <p>
            Quiz progress, history, bookmarks, notes, saved sessions, theme and your
            analytics choice are stored in your browser&apos;s local storage. They are not
            synced to an account or included in the PCEP database. They remain until you
            reset them in the application or clear this site&apos;s browser data.
          </p>
        </section>

        <section className="mt-7 space-y-3" aria-labelledby="service-heading">
          <h2 id="service-heading" className="text-xl font-semibold">
            Requests needed to provide and protect the service
          </h2>
          <p>
            The quiz API receives question and choice identifiers long enough to return
            feedback. It does not create learner accounts or store submitted answers,
            scores, notes or code. The Python runner executes in your browser.
          </p>
          <p>
            Cloudflare and the server necessarily process connection metadata such as IP
            address, request time, path, response status and security signals to deliver
            the site, rate-limit abuse and investigate incidents. PCEP&apos;s structured
            access log excludes URL query strings and is rotated daily, with at most 14
            rotated files plus the current file. Error and provider security logs can
            contain limited network metadata.
          </p>
          <p>
            This processing is based on the controller&apos;s legitimate interests in
            operating a secure, reliable public educational service (GDPR Article
            6(1)(f)). Raw PCEP Nginx logs are normally removed within 15 days unless a
            specific security incident requires a restricted evidence copy for longer.
          </p>
        </section>

        <section className="mt-7 space-y-3" aria-labelledby="analytics-heading">
          <h2 id="analytics-heading" className="text-xl font-semibold">
            Optional analytics
          </h2>
          <p>
            Analytics is off until you explicitly allow it and remains off when your
            browser sends Do Not Track. The self-hosted Umami service records page path,
            referrer domain, browser, operating system, device and approximate location.
            It uses network information to form a rotating anonymous session but does not
            store the IP address. Search parameters and URL fragments are excluded; no
            cookies, distinct user ID, quiz answer or custom learner event is sent.
          </p>
          <p>
            The legal basis is consent (GDPR Article 6(1)(a)). Analytics events and
            sessions for PCEP are automatically removed after 180 days. You can refuse or
            withdraw consent below without losing any feature.
          </p>
          <AnalyticsPreferences />
        </section>

        <section className="mt-7 space-y-3" aria-labelledby="providers-heading">
          <h2 id="providers-heading" className="text-xl font-semibold">
            Providers and transfers
          </h2>
          <p>
            Cloudflare provides the public proxy, network protection and tunnel to the
            self-managed server. Cloudflare may process connection and network-error
            information on its global infrastructure under its{' '}
            <a
              className="underline"
              href="https://www.cloudflare.com/cloudflare-customer-dpa/"
              rel="noreferrer"
            >
              data-processing terms
            </a>{' '}
            and{' '}
            <a
              className="underline"
              href="https://www.cloudflare.com/privacypolicy/"
              rel="noreferrer"
            >
              privacy policy
            </a>
            . Umami and the quiz database are self-hosted. PCEP does not sell learner data
            or use it for advertising.
          </p>
        </section>

        <section className="mt-7 space-y-3" aria-labelledby="rights-heading">
          <h2 id="rights-heading" className="text-xl font-semibold">
            Your choices and rights
          </h2>
          <p>
            Depending on the circumstances, you may request access, correction, deletion,
            restriction or objection and may withdraw analytics consent at any time.
            Because PCEP has no accounts and analytics is anonymous, include the
            approximate date, time and page in a request if you want us to investigate a
            particular record. You may also complain to Romania&apos;s National
            Supervisory Authority for Personal Data Processing ({' '}
            <a
              className="underline"
              href="https://www.dataprotection.ro/"
              rel="noreferrer"
            >
              ANSPDCP
            </a>
            ).
          </p>
          <p>
            There is no advertising profile, automated decision with legal effect or
            cross-site tracking. This notice will be updated before PCEP introduces an
            account, payment, synchronization or materially different use of data.
          </p>
        </section>

        <p className="mt-8">
          <a className="font-semibold underline" href="/">
            Return to PCEP Quiz
          </a>
        </p>
      </div>
    </main>
  )
}
