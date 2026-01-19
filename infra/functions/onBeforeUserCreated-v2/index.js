const gcipCloudFunctions = require('gcip-cloud-functions');
const authClient = new gcipCloudFunctions.Auth();

// 1. Define allowed domains
const APPROVED_DOMAINS = [
  "hit8.io",
  "acceconsult.be",
  "opgroeien.be"
];

// 2. Define specific allowed emails (exceptions for other domains)
const APPROVED_EMAILS = [
];

exports.onBeforeUserCreated = authClient.functions().beforeCreateHandler((user, context) => {
  const email = user.email;
  
  if (!email) {
    throw new gcipCloudFunctions.https.HttpsError('invalid-argument', 'Email is required');
  }
  
  const emailDomain = email.split("@")[1]?.toLowerCase();
  
  // Check if domain is in approved list
  const isApprovedDomain = APPROVED_DOMAINS.includes(emailDomain);
  
  // Check if specific email is in approved list
  const isApprovedEmail = APPROVED_EMAILS.includes(email.toLowerCase());
  
  const isApproved = isApprovedDomain || isApprovedEmail;
  
  // Optional: Reject users who are not approved
  if (!isApproved) {
    throw new gcipCloudFunctions.https.HttpsError(
      'permission-denied', 
      `Unauthorized email domain: ${email}`
    );
  }
  
  return {
    customClaims: {
      approved: isApproved
    }
  };
});
