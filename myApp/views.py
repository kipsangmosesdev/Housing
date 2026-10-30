import json
import re
from datetime import timedelta, timezone
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.staticfiles.finders import find as find_static_file
from django.core.mail import send_mail
from django.db.models import Avg
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import context
from django.utils import timezone
from itsdangerous import URLSafeTimedSerializer

from myApp import models
from myApp.models import registerUser

from .forms import (CommentForm, EditLandlordProfileForm, EditUserEmailForm,
                    LandlordProfileForm, LandlordUserForm, PaymentForm,
                    PropertyForm, PropertyImageFormSet, SystemRatingForm, TenantEditForm,
                    TenantPaymentForm, TenantRegistrationForm,
                    TransporterRegistrationForm)
from .models import (Amenity, GeneralTip, Payment, Property, PropertyImage, PropertyType,
                     PropertyView, Rating, SystemRating, Tenant, Transporter,
                     TransporterSubscription, adminUpdate)


def service_worker(request):
    """Serve the PWA worker at the origin root so it can control the full site."""
    worker_path = find_static_file("myApp/js/service-worker.js")
    if not worker_path:
        raise Http404("Service worker not found")

    with open(worker_path, "rb") as worker_file:
        response = HttpResponse(worker_file.read(), content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def register_landlord(request):
    """
    Handles landlord registration.
    - Step 1: Display blank registration forms (GET request).
    - Step 2: Process submitted form data (POST request).
    - Step 3: Validate inputs, check duplicates, save User + Profile.
    """

    if request.method == 'POST':
        # Bind forms with POST data (and files for profile picture, ID scan, etc.)
        user_form = LandlordUserForm(request.POST)
        profile_form = LandlordProfileForm(request.POST, request.FILES)

        #  Validate both forms
        if user_form.is_valid() and profile_form.is_valid():

            # -------------------
            # Duplicate checks
            # -------------------

            # Check if email already exists in the system
            email = user_form.cleaned_data['email']
            if models.User.objects.filter(email=email).exists():
                messages.error(request, "This email is already registered. Please use another.")
                return redirect('landlord_register')

            # Check if ID number is already registered
            id_number = profile_form.cleaned_data['id_number']
            if models.registerUser.objects.filter(id_number=id_number).exists():
                messages.error(request, "This ID number is already in use.")
                return redirect('landlord_register')

            # -------------------
            # Save User object
            # -------------------
            user = user_form.save(commit=False)  # Create User instance but don’t save yet
            user.set_password(user_form.cleaned_data['password'])  # Hash the password
            user.save()  # Now save to DB

            # -------------------
            # Save Profile (registerUser)
            # -------------------
            profile = profile_form.save(commit=False)
            profile.user = user  # Link landlord profile to the created user
            profile.save()

            messages.success(request, "Registration successful! Please log in.")
            return redirect('unified_login')  # Redirect to login after registration

        else:
            # Forms are not valid — show error messages automatically
            messages.error(request, "Please correct the errors below.")

    else:
        # GET request: show blank forms for the first time
        user_form = LandlordUserForm()
        profile_form = LandlordProfileForm()

    # Render template with forms (either blank or pre-filled if invalid submission)
    return render(request, 'myApp/landlord_register.html', {
        'user_form': user_form,
        'profile_form': profile_form
    })


def logout_user(request):
    logout(request)
    # messages.success(request, "You have been logged out.")
    return redirect('tenant_landing')


def home(request):
    return render(request, 'myApp/home.html')
    
 

from django.db.models import Avg, Count
from django.shortcuts import redirect, render

from myApp.models import Payment, Property, PropertyView, registerUser


@login_required(login_url='login')
def landlord_dashboard(request):
    """
    Landlord Dashboard View
    -----------------------
    - Ensures landlord is authenticated and exists in the system.
    - Checks subscription (or free trial) validity.
    - Collects property stats: availability, views, comments, ratings, invoices.
    - Prepares data for charts (views per property).
    - Shows recent tenant activity.
    - Selects template based on landlord type (individual, company, agent).
    """

    # -------------------------------
    # 1. Get the current landlord
    # -------------------------------
    try:
        landlord = registerUser.objects.get(user=request.user)
    except registerUser.DoesNotExist:
        # If no landlord profile exists, force login
        return redirect('login')

    # -------------------------------
    # 2. Check subscription or free trial
    # -------------------------------
    # Get the most recent successful payment
    latest_payment = (
        Payment.objects
        .filter(landlord=landlord, is_successful=True)
        .order_by('-timestamp')
        .first()
    )
    expiry_date = latest_payment.expiry_date if latest_payment else None
    amount = landlord.subscription_fee()
    # Handle free trial (if active and not expired)
    if landlord.is_free_trial and landlord.trial_expiry:
        if landlord.trial_expiry > timezone.now():
            expiry_date = landlord.trial_expiry
            # Mock a "virtual payment" to simplify dashboard logic
            latest_payment = Payment(
                landlord=landlord,
                is_successful=True,
                expiry_date=landlord.trial_expiry,
                plan=None
            )
        else:
            # Trial expired → disable free trial
            landlord.is_free_trial = False
            landlord.save()

    # Enforce subscription check (must be active and not expired)
    if not latest_payment or not latest_payment.expiry_date or latest_payment.expiry_date < timezone.now():
        return render(request, 'myApp/subscription_expired.html', {'landlord': landlord})
    
    # -------------------------------
    # 3. Collect property statistics
    # -------------------------------
    landlord_properties = Property.objects.filter(landlord=landlord)

    total_properties = landlord_properties.count()
    available_properties = landlord_properties.filter(is_available=True).count()
    occupied_properties = landlord_properties.filter(is_available=False).count()

    
    # Define the time window (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Count property views within the last 30 days
    recent_views = PropertyView.objects.filter(
        property__in=landlord_properties,
        viewed_on__gte=thirty_days_ago
    ).count()

    total_views = PropertyView.objects.filter(property__in=landlord_properties).count()
    total_invoices = Payment.objects.filter(landlord=landlord).count()
    total_comments = sum(
        property.comments.filter(is_approved=True).count()
        for property in landlord_properties
    )

    # Calculate average rating across all landlord properties
    average_rating = (
        sum(
            property.ratings.aggregate(Avg('score'))['score__avg'] or 0
            for property in landlord_properties
        ) / total_properties
        if total_properties > 0 else 0
    )

    # -------------------------------
    # 4. Data for charts
    # -------------------------------
    property_views = (
        PropertyView.objects
        .filter(property__in=landlord_properties)
        .values('property__title')
        .annotate(view_count=Count('id'))
        .order_by('-view_count')
    )
    chart_labels = [item['property__title'] for item in property_views]
    chart_data = [item['view_count'] for item in property_views]

    # -------------------------------
    # 5. Recent tenant activity
    # -------------------------------
    recent_property_views = (
        PropertyView.objects
        .filter(property__in=landlord_properties)
        .select_related('tenant__user', 'property')
        .order_by('-viewed_on')[:20]
    )

    # -------------------------------
    # 6. Template selection
    # -------------------------------
    template_map = {
        'individual': 'myApp/dashboard_individual.html',
        'company': 'myApp/dashboard_company.html',
        'agent': 'myApp/dashboard_agent.html',
    }
    template = template_map.get(landlord.landlord_type, 'myApp/dashboard_default.html')

    # -------------------------------
    # 7. Render response
    # -------------------------------
    context = {
        'landlord': landlord,
        'payment': latest_payment,
        'expiry_date': latest_payment.expiry_date,
        'payment_status': latest_payment.is_successful,
        'date_expires': expiry_date,

        # Stats
        'total_properties': total_properties,
        'available_properties': available_properties,
        'occupied_properties': occupied_properties,
        'total_views': total_views,
        'total_invoices': total_invoices,
        'total_comments': total_comments,
        'average_rating': round(average_rating, 1) if total_properties > 0 else 0,
        # 'total_favorites': total_favorites,  # Uncomment when favorites are implemented

        # Chart data
        'property_views': property_views,
        'chart_labels': chart_labels,
        'chart_data': chart_data,

        # Recent tenant views
        'recent_property_views': recent_property_views,
        'amount':amount,
        'recent_views':recent_views,
    }

    return render(request, template, context)


from myApp.forms import PropertyForm
from myApp.models import Property, PropertyImage, registerUser


@login_required(login_url='login')
def post_property(request):
    """
    Allows a landlord to post a new property.
    - Enforces posting limits based on landlord type (individual, company, agent).
    - Handles property creation with optional multiple image uploads.
    """

    # -----------------------------
    # 1. Get the current landlord
    # -----------------------------
    landlord = get_object_or_404(registerUser, user=request.user)

    # -----------------------------
    # 2. Enforce posting limits
    # -----------------------------
    property_limits = {
        'individual': 1,   # Individual landlords can post 1 property
        'company': 3,      # Companies can post up to 3
        'agent': 5         # Agents can post up to 5
    }
    # Default to 0 if landlord type is unknown
    property_limit = property_limits.get(landlord.landlord_type, 0)

    current_property_count = Property.objects.filter(landlord=landlord).count()

    if current_property_count >= property_limit:
        messages.error(
            request,
            f"You have reached your limit of {property_limit} properties for your plan."
        )
        return redirect('my_properties')  # Could also redirect to dashboard

    # Remaining posting slots
    remaining_slots = property_limit - current_property_count
    messages.info(request, f"You have {remaining_slots} posting slots remaining.")

    # -----------------------------
    # 3. Handle form submission
    # -----------------------------
    if request.method == 'POST':
        form = PropertyForm(request.POST)
        uploaded_images = request.FILES.getlist('images')  # Handle multiple images

        if form.is_valid():
            # Create property object but don't save yet
            property_obj = form.save(commit=False)
            property_obj.landlord = landlord
            property_obj.save()

            # Save Many-to-Many fields (like amenities)
            form.save_m2m()

            # Attach uploaded images to the property
            for image in uploaded_images:
                PropertyImage.objects.create(property=property_obj, image=image)

            messages.success(request, "Property posted successfully.")
            return redirect('landlord_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PropertyForm()

    # -----------------------------
    # 4. Render response
    # -----------------------------
    return render(request, 'myApp/post_property.html', {
        'form': form,
        'remaining': remaining_slots,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    })
    


@login_required(login_url='login')
def my_properties(request):
    landlord = request.user.registeruser  # Link via OneToOneField
    # properties of landlords on free trial or paid
    properties = Property.objects.filter(landlord=landlord).order_by('-date_posted')
    
    return render(request, 'myApp/my_properties.html', {'properties': properties})

# @login_required(login_url='login')

from collections import Counter

from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from myApp.models import Tenant, registerUser  # Adjust if needed

from .forms import CommentForm, RatingForm
from .models import Comment, FavoriteProperty, Property, PropertyView, Rating

# Unified Login View

import logging
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.contrib import messages

# Logger for login attempts
login_logger = logging.getLogger('myApp.login')

def get_client_ip(request):
    """Extract client IP address safely."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def unified_login(request):
    form = AuthenticationForm(request, data=request.POST or None)
    next_url = request.GET.get('next')

    if request.method == 'POST':
        username = request.POST.get('username')
        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Determine user role
            role = (
                "landlord" if hasattr(user, 'registeruser') else
                "tenant" if hasattr(user, 'tenant') else
                "transporter" if hasattr(user, 'transporter') else
                "unknown"
            )

            # Log successful login
            login_logger.info(
                f"SUCCESS | username={username} | role={role} | ip={ip} | agent={user_agent}"
            )

            # Redirect to ?next=
            if next_url:
                return redirect(next_url)

            # Redirect based on role
            if role == "landlord":
                messages.success(request, f"Welcome {user.username}, landlord!")
                return redirect('landlord_dashboard')
            elif role == "tenant":
                messages.success(request, f"Welcome {user.username}, tenant!")
                return redirect('tenant_dashboard')
            elif role == "transporter":
                messages.success(request, f"Welcome {user.username}, transporter!")
                return redirect('transporter_dashboard')
            else:
                messages.warning(request, "You are not assigned a role.")
                return redirect('login')

        else:
            # Log failed attempt
            login_logger.info(
                f"FAILED | username={username} | ip={ip} | agent={user_agent}"
            )

            messages.error(request, "Invalid username or password. Please try again.")

    return render(request, 'myApp/login.html', {'form': form})


# end of unified login



def landlord_tenant_signup(request):
    return render(request, 'myApp/landlord_tenant_signup.html')

def property_detail(request, pk):
    try:
        property_obj = Property.objects.get(pk=pk)
    except Property.DoesNotExist:
        raise Http404("Property not found")

    # Restrict access to unapproved properties
    if not property_obj.is_approved:
        if not request.user.is_authenticated or not hasattr(request.user, 'registeruser'):
            raise PermissionDenied("This property is not approved yet.")
        if property_obj.landlord != request.user.registeruser:
            raise PermissionDenied("You don't have permission to view this property.")

    # Approved Comments
    comments = property_obj.comments.filter(is_approved=True).select_related('user').order_by('-timestamp')
    ratings = property_obj.ratings.all()
    average_rating = ratings.aggregate(score__avg=Avg('score'))['score__avg'] or 0

    # verified
    is_verified = property_obj.is_verified
    is_featured = property_obj.featured
    
    # Rating distribution (5 to 1 stars)
    score_counts = Counter(ratings.values_list('score', flat=True))
    rating_distribution = [score_counts.get(i, 0) for i in range(5, 0, -1)]

    # Forms and flags
    comment_form = CommentForm()
    rating_form = None
    user_rating = None
    is_favorite = False

    if request.user.is_authenticated:
        if hasattr(request.user, 'tenant'):
            tenant = request.user.tenant

            # Track property view
            PropertyView.objects.update_or_create(
                tenant=tenant,
                property=property_obj,
                defaults={'viewed_on': timezone.now()}
            )

            # Check if it's a favorite
            is_favorite = FavoriteProperty.objects.filter(
                tenant=tenant,
                property=property_obj
            ).exists()

        # Handle forms
        if request.method == 'POST':
            if 'comment_submit' in request.POST:
                comment_form = CommentForm(request.POST)
                if comment_form.is_valid():
                    comment = comment_form.save(commit=False)
                    comment.property = property_obj
                    comment.user = request.user
                    comment.save()
                    return redirect('property_detail', pk=pk)

            elif 'rating_submit' in request.POST:
                user_rating = Rating.objects.filter(user=request.user, property=property_obj).first()
                rating_form = RatingForm(request.POST, instance=user_rating)
                if rating_form.is_valid():
                    rating = rating_form.save(commit=False)
                    rating.property = property_obj
                    rating.user = request.user
                    rating.save()
                    return redirect('property_detail', pk=pk)
        else:
            user_rating = Rating.objects.filter(user=request.user, property=property_obj).first()
            rating_form = RatingForm(instance=user_rating)

    # Categorized Amenities
    categorized_amenities = {

    "Security & Access": [
        "24/7 Security",
        "24/7 CCTV Surveillance",
        "Security Guard",
        "Security Patrols",
        "Security Lighting",
        "Security Alarm System",
        "Alarm System",
        "Emergency Alert System",
        "Emergency Assembly Point",
        "Emergency Exit",
        "Emergency Lighting",
        "Emergency Staircase",
        "Fire Alarm",
        "Fire Escape",
        "Fire Extinguishers",
        "Fire Hose Reels",
        "Sprinkler System",
        "Smoke Detectors",
        "Carbon Monoxide Detector",
        "Electric Fence",
        "Perimeter Wall",
        "Fenced Compound",
        "Gated Community",
        "Boom Gate",
        "Double Gate",
        "Guard House",
        "Guard Dogs",
        "Biometric Access",
        "RFID / Keycard Access",
        "Smart Lock",
        "Video Doorbell",
        "Intercom System",
        "Motion Sensor Lighting",
        "Visitor Management System",
        "Wheelchair Accessible",
        "Safe",
        "First Aid Kit",
        "Panic Alarm"
    ],

    "Interior Features": [
        "Air Conditioning",
        "Ceiling Fan",
        "Natural Lighting",
        "Sliding Doors",
        "Sliding Windows",
        "Soundproof Walls",
        "Double Glazed Windows",
        "Walk-in Closet",
        "Built-in Wardrobes",
        "Wardrobe",
        "Wall Mirrors",
        "Fitted Cabinets",
        "Curtain Rods Installed",
        "Living Room",
        "Dining Area",
        "Home Office",
        "Dedicated Workspace",
        "Private Entrance",
        "Private Terrace",
        "Private Balcony",
        "Balcony",
        "Balcony View",
        "Fireplace",
        "Luxury Finishes",
        "POP Ceiling",
        "PVC Ceiling",
        "Gypsum Ceiling",
        "Acoustic Ceiling",
        "Metal Ceiling",
        "Wooden Ceiling",
        "Coffered Ceiling",
        "Underfloor Heating",
        "TV Wall"
    ],

    "Technology & Smart Features": [
        "WiFi",
        "Internet",
        "Fiber Internet",
        "Cable TV Ready",
        "Satellite TV",
        "DSTV",
        "Netflix Ready",
        "Wall-Mounted TV Points",
        "Smart Lighting",
        "Smart Doorbell",
        "Smart Lock",
        "Smart Thermostat",
        "Smart Water Leak Sensors",
        "Home Automation",
        "Electricity - Postpaid",
        "Electricity - Prepaid",
        "Prepaid Electricity"
    ],

    "Green & Sustainable Living": [
        "Solar Panels",
        "Solar Water Heater",
        "Solar Power Backup",
        "Rainwater Harvesting",
        "Greywater Recycling",
        "Wastewater Treatment",
        "Water Pressure Booster",
        "Reliable Water Supply",
        "Water Backup",
        "Water Storage Tank",
        "Water Purifier",
        "Energy-Efficient Appliances",
        "Composting Facility",
        "Recycling Center",
        "Recycling Pickup"
    ],

    "Kitchen Features": [
        "Modern Kitchen",
        "Open Kitchen",
        "Kitchen Island",
        "Countertop Kitchen",
        "Built-in Kitchen Appliances",
        "Kitchen Cabinets",
        "Kitchen Pantry",
        "Pantry",
        "Breakfast Bar",
        "Dishwasher",
        "Double Sink",
        "Single Sink",
        "Kitchen Chimney",
        "Gas Cooker Connection",
        "Microwave Space",
        "Refrigerator Space"
    ],

    "Bathroom Features": [
        "Ensuite Bathroom",
        "Shared Bathroom",
        "Shared Toilet",
        "Guest Cloakroom",
        "Bathtub",
        "Hot Shower",
        "Shower Cubicle",
        "Heated Water System",
        "Anti-slip Tiles",
        "Squat Toilet",
        "Sitting Toilet",
        "Hair Dryer",
        "Toiletries Included"
    ],

    "Laundry": [
        "Laundry Room",
        "Laundry Machine",
        "Laundry Drying Area",
        "Cleaning Services",
        "Housekeeping",
        "Iron",
        "Ironing Board",
        "Ironing Station"
    ],

    "Shared Amenities": [
        "Reception Desk",
        "24-Hour Reception",
        "24-Hour Concierge",
        "Resident Caretaker",
        "Caretaker",
        "Property Manager",
        "Resident Support Staff",
        "Shared Kitchen",
        "Shared Study Area",
        "Conference Room",
        "Business Center",
        "Library",
        "Restaurant",
        "Coffee Shop",
        "Club House",
        "Game Room",
        "Entertainment Area",
        "Gym",
        "Fitness Center",
        "Spa",
        "Sauna",
        "Steam Room",
        "Yoga Area",
        "Children's Play Area",
        "Children's Swimming Pool",
        "Daycare",
        "Visitor Parking",
        "Guest Parking",
        "Elevator",
        "Lift",
        "Service Elevator",
        "Pet Friendly",
        "Luggage Storage"
    ],

    "Luxury & Extra Comfort": [
        "Fully Furnished",
        "Semi-Furnished",
        "Private Gym",
        "Private Pool",
        "Swimming Pool",
        "Infinity Pool",
        "Jacuzzi",
        "Hot Tub",
        "Rooftop Terrace",
        "Generator Power Backup",
        "Power Backup",
        "Fireplace",
        "Luxury Finishes",
        "Guest House",
        "Servant Quarters",
        "Room Service",
        "Mini Bar"
    ],

    "Parking & Storage": [
        "Parking",
        "Covered Parking",
        "Open Parking",
        "Garage",
        "Visitor Parking",
        "Guest Parking",
        "Electric Vehicle Charging Station",
        "Car Wash Area",
        "Storage Room"
    ],

    "Flooring": [
        "Tile Flooring",
        "Natural Wood Flooring",
        "Hardwood Flooring",
        "Marble Flooring",
        "Vinyl Flooring",
        "Cement Screed Flooring",
        "Granite Countertops"
    ],

    "Outdoor & Compound Features": [
        "Garden",
        "Private Garden",
        "Garden View",
        "Green Space",
        "Beautiful Landscaping",
        "Paved Compound",
        "Driveway",
        "Outdoor Sitting Area",
        "Outdoor Dining Area",
        "Outdoor Shower",
        "Outdoor Grilling Area",
        "Gazebo",
        "Barbecue Area",
        "BBQ Grill",
        "Jogging Track",
        "Playground",
        "Basketball Court",
        "Tennis Court",
        "Squash Court",
        "Golf Course Nearby",
        "Beach Access",
        "Borehole Water",
        "Septic Tank",
        "Perimeter Lighting",
        "Rooftop Water Tank",
        "Clinic Nearby",
        "School Nearby",
        "Supermarket Nearby",
        "ATM Nearby",
        "Trash Collection",
        "Waste Collection"
    ]
}

    # Get property amenities as strings
    property_amenities = list(property_obj.amenities.values_list('name', flat=True))

    context = {
        'property': property_obj,
        'comments': comments,
        'comment_form': comment_form,
        'ratings': ratings,
        'rating_form': rating_form,
        'average_rating': round(average_rating, 1),
        'user_rating': user_rating,
        'is_favorite': is_favorite,
        'rating_distribution': rating_distribution,
        'categorized_amenities': categorized_amenities,
        'property_amenities': property_amenities,
        'is_verified':is_verified,
        'featured':is_featured,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    }

    return render(request, 'myApp/property_detail.html', context)


import bleach
from bleach.css_sanitizer import CSSSanitizer

# Allowed HTML tags
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'i',
    'b', 'u', 'blockquote', 'code', 'pre', 'span', 'div',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
]

# Allowed HTML attributes
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target'],
    'img': ['src', 'alt', 'width', 'height', 'style'],
    'span': ['style'],
    'div': ['style'],
    'p': ['style'],
    'table': ['style', 'border', 'cellpadding', 'cellspacing'],
    'th': ['style'],
    'td': ['style']
}

# Allowed CSS properties for inline styles
css_sanitizer = CSSSanitizer(
    allowed_css_properties=['color', 'font-family', 'background-color', 'text-align']
)


@login_required(login_url='login')
def edit_property(request, pk):
    property = get_object_or_404(Property, pk=pk)
    form = PropertyForm(request.POST or None, request.FILES or None, instance=property)
    formset = PropertyImageFormSet(request.POST or None, request.FILES or None, queryset=PropertyImage.objects.none())

    if request.method == 'POST': 
        if form.is_valid() and formset.is_valid():
            updated_property = form.save(commit=False)

            # ✅ Sanitize CKEditor HTML
            updated_property.description = bleach.clean(
                form.cleaned_data['description'],
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                strip=True,
                css_sanitizer=css_sanitizer
            )

            # ✅ Handle Property Document Upload / Update
            if 'property_document' in request.FILES:
                updated_property.property_document = request.FILES['property_document']

            # ✅ Update Document Caption
            document_caption = request.POST.get('document_caption', '')
            updated_property.document_caption = document_caption

            updated_property.save()
            form.save_m2m()

            # ✅ Handle existing image updates/deletes
            for image in updated_property.images.all():
                caption_key = f'image_caption_{image.id}'
                delete_key = f'delete_image_{image.id}'
                replace_key = f'replace_image_{image.id}'

                if delete_key in request.POST:
                    image.delete()
                    continue

                new_caption = request.POST.get(caption_key)
                if new_caption is not None:
                    image.caption = new_caption

                if replace_key in request.FILES:
                    image.image = request.FILES[replace_key]

                image.save()

            # ✅ Save new formset images
            for form_data in formset.cleaned_data:
                if form_data:
                    PropertyImage.objects.create(
                        property=updated_property,
                        image=form_data['image'],
                        caption=form_data.get('caption', '')
                    )

            #  Handle multiple new uploads
            for img in request.FILES.getlist('new_images'):
                PropertyImage.objects.create(
                    property=updated_property,
                    image=img,
                    caption=request.POST.get('default_caption', '')
                )

            messages.success(request, "Property updated successfully.")
            return redirect('edit_property', pk=property.pk)

    return render(request, 'myApp/edit_property.html', {
        'form': form,
        'formset': formset,
        'property': property,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
        'lat': property.latitude or -1.2921,  # fallback if null
        'lng': property.longitude or 36.8219
    })


# image upload
from django.forms import modelformset_factory

from .models import PropertyImage

PropertyImageFormSet = modelformset_factory(
    PropertyImage,
    fields=('image', 'caption'),
    extra=3,  # allow 3 images at a time
    can_delete=False
)

@login_required(login_url='login')
def delete_property(request, pk):
    property_obj = get_object_or_404(Property, pk=pk, landlord=request.user.registeruser)

    if request.method == 'POST':
        property_obj.delete()
        messages.success(request, "Property deleted successfully.")
        return redirect('my_properties')

    return render(request, 'myApp/delete_property.html', {'property': property_obj})


from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Subquery, DateTimeField, OuterRef
from .models import Property, Payment  # Adjust import paths as needed

def property_map_view(request):
    # Check if this is an AJAX dynamic map fetch
    is_ajax = request.GET.get('ne_lat') is not None

    # Subquery: get latest expiry_date per landlord
    latest_payment = Payment.objects.filter(
        landlord=OuterRef('landlord'),
        is_successful=True
    ).order_by('-expiry_date').values('expiry_date')[:1]

    now = timezone.now()

    # Queryset with annotated landlord payment expiry date
    properties = (
        Property.objects.annotate(
            landlord_expiry=Subquery(latest_payment, output_field=DateTimeField())
        )
        .filter(
            is_approved=True,
            landlord__is_verified=True,
        )
        .filter(
            # Paid landlords: is_paid AND payment not expired
            Q(
                landlord__is_paid=True,
                landlord_expiry__isnull=False,
                landlord_expiry__gte=now
            )
            |
            # Trial landlords: is_free_trial AND trial_expiry not expired
            Q(
                landlord__is_free_trial=True,
                landlord__trial_expiry__isnull=False,
                landlord__trial_expiry__gte=now
            )
        )
        .select_related("landlord")
        .order_by('-date_posted')
    )

    # ---------------------------------------------------------
    # Branch 1: AJAX Bounding Box Fetch
    # ---------------------------------------------------------
    if is_ajax:
        try:
            ne_lat = float(request.GET.get('ne_lat'))
            ne_lng = float(request.GET.get('ne_lng'))
            sw_lat = float(request.GET.get('sw_lat'))
            sw_lng = float(request.GET.get('sw_lng'))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid coordinates'}, status=400)

        # The map is a room-finding view: return vacant listings for its visible area.
        if request.GET.get('available_only') == '1':
            properties = properties.filter(is_available=True)

        # Handle dateline wrapping if needed
        if sw_lng <= ne_lng:
            lng_filter = Q(longitude__gte=sw_lng, longitude__lte=ne_lng)
        else:
            lng_filter = Q(longitude__gte=sw_lng) | Q(longitude__lte=ne_lng)

        # Apply spatial bounding box query
        properties = properties.filter(
            latitude__gte=sw_lat,
            latitude__lte=ne_lat,
            latitude__isnull=False,
            longitude__isnull=False
        ).filter(lng_filter)[:500]  # Cap result set for safety

        # Prefetch images for efficiency
        properties = properties.prefetch_related('images')

        data = []
        for prop in properties:
            first_img = prop.images.first()
            img_url = first_img.image.url if first_img else '/static/myApp/images/lycs-architecture-kUdbEEMcRwE-unsplash.jpg'

            data.append({
                'id': prop.id,
                'lat': prop.latitude,
                'lng': prop.longitude,
                'title': prop.title,
                'rent': prop.rent,
                'is_available': prop.is_available,
                'img_url': img_url,
                'details_url': f"/dashboard/property/{prop.id}/",
                'city': prop.city,
                'estate': prop.estate,
                'bedrooms': prop.bedrooms,
                'bathrooms': prop.bathrooms,
                'is_verified': prop.is_verified,
            })

        return JsonResponse({'properties': data})

    # ---------------------------------------------------------
    # Branch 2: Standard HTML Page Render (Initial Load)
    # ---------------------------------------------------------
    return render(request, 'myApp/property_map.html', {
        'properties': [],  # Map JS will fetch points dynamically via AJAX
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    })

@login_required(login_url='login')
def landlord_profile(request):
    landlord = registerUser.objects.get(user=request.user)
    return render(request, 'myApp/profile.html', {'landlord': landlord})

# Edit profile
# Create the token serializer
serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

@login_required(login_url='login')
def edit_landlord_profile(request):
    landlord = registerUser.objects.get(user=request.user)
    user = request.user

    if request.method == 'POST':
        form1 = EditLandlordProfileForm(request.POST, request.FILES, instance=landlord)
        form2 = EditUserEmailForm(request.POST, instance=user)

        new_email = request.POST.get('email')

        if form1.is_valid() and form2.is_valid():
            form1.save()

            if new_email and new_email != user.email:
                # Generate token with new email
                token = serializer.dumps(new_email, salt='email-confirm')
                confirm_url = request.build_absolute_uri(f"/profile/confirm-email/{token}/")

                # Send confirmation email
                send_mail(
                    'Confirm Your New Email Address',
                    f'Click the link to confirm your new email: {confirm_url}',
                    settings.DEFAULT_FROM_EMAIL,
                    [new_email],
                    fail_silently=False
                )

                messages.info(request, "A confirmation email has been sent to your new address.")
                return redirect('landlord_profile')
            else:
                form2.save()
                messages.success(request, "Profile updated successfully.")
                return redirect('landlord_profile')

    else:
        form1 = EditLandlordProfileForm(instance=landlord)
        form2 = EditUserEmailForm(instance=user)

    return render(request, 'myApp/edit_profile.html', {
        'form1': form1,
        'form2': form2
    })


# View for Confirming the Email
from django.http import HttpResponseBadRequest


def confirm_new_email(request, token):
    try:
        email = serializer.loads(token, salt='email-confirm', max_age=3600)
        user = request.user
        user.email = email
        user.save()

        # Update verification status
        landlord = registerUser.objects.get(user=user)
        landlord.is_verified = True
        landlord.save()

        messages.success(request, "Your email address has been updated and verified.")
        return redirect('landlord_profile')
    except Exception:
        return HttpResponseBadRequest("Invalid or expired confirmation link.")

# Payment view
@login_required(login_url='login')
def payment_page(request):
    landlord = get_object_or_404(registerUser, user=request.user)
    fee = landlord.subscription_fee()
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.landlord = landlord
            payment.save()
            messages.success(request, "Payment submitted successfully. It will be reviewed shortly.")
            return redirect('landlord_dashboard')
    else:
        form = PaymentForm()

    return render(request, 'myApp/payment.html', {'form': form, 'landlord': landlord, 'amount': fee})


# Invoice View
@login_required(login_url='login')
def invoice_view(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, landlord__user=request.user)
    return render(request, 'myApp/invoice.html', {'payment': payment})


# All invoices 
@login_required(login_url='login')
def landlord_invoice_list(request):
    invoices = Payment.objects.filter(landlord__user=request.user).order_by('-timestamp')
    return render(request, 'myApp/invoice_list.html', {'invoices': invoices})


from django.core.paginator import Paginator
from django.db.models import Avg, Count, DateTimeField, OuterRef, Q, Subquery

# Landing Page View
from .models import Payment, Property, SystemRating, adminUpdate


def tenant_landing_page(request):
    """
    Tenant landing: shows featured properties and a paginated list of all approved/available properties
    - Only properties whose landlords are 'valid' are shown (valid = active paid subscription OR active free trial)
    - We annotate each property with:
        * landlord_expiry  -> from the latest successful Payment (via Subquery)
        * landlord_plan    -> landlord type (agent/company/individual) from the payment plan (via Subquery)
        * avg_rating       -> average of related ratings (Avg of ratings__score)
    """

    # Subquery: the landlord's latest successful payment that hasn't expired yet.
    latest_payment_qs = (
        Payment.objects
        .filter(
            landlord=OuterRef("landlord"),      # link Payment.landlord to this property's landlord
            status="Success",
            expiry_date__gte=timezone.now()    # only non-expired payments
        )
        .order_by("-expiry_date")
    )

    # A landlord is considered "valid" when:
    #  - they are marked as paid and the latest payment expiry is still in the future (landlord_expiry),
    #    OR
    #  - they are on a free trial and the landlord model's trial_expiry is in the future.
    # N/b: this uses an annotated field 'landlord_expiry' (added below) and fields on the landlord model
    valid_landlord_q = (
        Q(landlord__is_paid=True, landlord_expiry__gte=timezone.now())
        | Q(landlord__is_free_trial=True, landlord__trial_expiry__gte=timezone.now())
    )

    # Build the base annotated queryset once (avoid repeating annotate/filter logic).
    # We add:
    #  - landlord_expiry (from payment subquery)
    #  - landlord_plan (from payment subquery -> plan__landlord_type)
    #  - avg_rating (Avg of ratings__score)
    
    # Featured properties only
    base_qs = (
        Property.objects
        .annotate(
            landlord_expiry=Subquery(latest_payment_qs.values("expiry_date")[:1]),
            landlord_plan=Subquery(latest_payment_qs.values("plan__landlord_type")[:1]),
            avg_rating=Avg("ratings__score"),
            total_comments=Count("comments", filter=Q(comments__is_approved=True), distinct=True)
        )
        .filter(
            is_available=True,
            is_approved=True,
            featured=True,
            landlord__is_verified=True,
        )
        .filter(valid_landlord_q)    # apply the paid/trial condition
        .prefetch_related("images")  # reduce queries when accessing images
        .order_by("-date_posted")
    )
    
    # All properties
    all_properties_qs = (
        Property.objects
        .annotate(
            landlord_expiry=Subquery(latest_payment_qs.values("expiry_date")[:1]),
            landlord_plan=Subquery(latest_payment_qs.values("plan__landlord_type")[:1]),
            avg_rating=Avg("ratings__score"),
            total_comments=Count("comments", filter=Q(comments__is_approved=True), distinct=True)
        )
        .filter(
            is_available=True,
            is_approved=True,
            featured=False,  # only non-featured here
            landlord__is_verified=True,
        )
        .filter(valid_landlord_q)    # apply the paid/trial condition
        .prefetch_related("images")  # reduce queries when accessing images
        .order_by("-date_posted")
    )

    # Featured properties: top 3 (most recent) from the base query
    # featured_properties = base_qs[:3]
    featured_properties = base_qs

    # All properties: paginated (6 per page)
    property_list = all_properties_qs  #  will be used by Paginator
    paginator = Paginator(property_list, 12)
    page_number = request.GET.get("page")
    all_properties = paginator.get_page(page_number)  # Page object
    
    # Admin updates (keeps existing logic)
    admin_updates = adminUpdate.objects.filter(is_active=True).order_by("-date_posted")[:2]

    # System ratings (aggregate & recent approved reviews)
    approved_ratings = SystemRating.objects.filter(is_approved=True)
    average_score = approved_ratings.aggregate(avg=Avg("score"))["avg"] or 0
    recent_reviews = approved_ratings.select_related("user").order_by("-timestamp")[:3]
    

    # get subscription plans
    subscription_plans = SubscriptionPlan.objects.all().order_by("price")
    
    context = {
        "featured_properties": featured_properties,
        "all_properties": all_properties,
        "average_score": round(average_score, 1),
        "recent_reviews": recent_reviews,
        "approved_ratings": approved_ratings,
        "total_reviews": approved_ratings.count(),
        "admin_updates": admin_updates,
        "subscription_plans": subscription_plans,
    }
    return render(request, "myApp/tenant_landing.html", context)

# Contact landlord view
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy

from myApp.models import (  # Tokens and properties are now under myApp
    Property, TokenWallet)

from .models import Property


@login_required(login_url=reverse_lazy('login'))
def contact_landlord(request, pk):
    # 1. Get the property
    property_obj = get_object_or_404(Property, pk=pk, is_available=True, is_approved=True)
    landlord = property_obj.landlord  # registerUser instance

    # 2. Ensure tenant has a token wallet
    wallet, _ = TokenWallet.objects.get_or_create(tenant=request.user)

    # Expire any tokens that have passed their expiry date
    expired_tokens = wallet.expire_tokens()

    # 3. Check if tenant has at least 1 Swift
    if wallet.tokens < 1:
        messages.warning(request, "You don't have enough Swifts to view this contact.")
        return redirect('mpesa:buy_token')  # Buy tokens view is still in mpesa app

    # 4. Deduct 1 Swift
    wallet.tokens -= 1
    wallet.save()

    # 5. Proceed to render landlord contact info
    messages.success(request, "1 Swift used to view contact.")
    return render(request, 'myApp/contact_landlord.html', {
        'property': property_obj,
        'landlord': landlord,
    })

# Tenant registration
def tenant_register(request):
    if request.method == 'POST':
        form = TenantRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Registration successful. You can now log in.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = TenantRegistrationForm()
    
    return render(request, 'myApp/tenant_register.html', {'form': form})



from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect


def tenant_logout(request):
    logout(request)
    return redirect('tenant_landing')  # Or redirect to 'landing_page' if you prefer

from django.shortcuts import render

from .models import (FavoriteProperty, PropertyView, Tenant, TokenTransaction,
                     TokenWallet)



@login_required(login_url='unified_login')
def tenant_dashboard(request):
    """
    Tenant Dashboard View
    ---------------------
    Displays key information to the logged-in tenant such as:
    - Active token balance and expiry details
    - Recent token transactions
    - Favorite and recently viewed properties
    """

    # 1 Get or create a wallet for the logged-in tenant.
    # If the wallet doesn’t exist, a new one will be created automatically.
    wallet, _ = TokenWallet.objects.get_or_create(tenant=request.user)

    # 2 Check and remove expired tokens (auto-handled in wallet model method).
    expired_tokens = wallet.expire_tokens()

    # 3 Retrieve the most recent token transaction for expiry reference.
    # If the tenant has ever bought tokens, get the expiry date of the latest one.
    last_transaction = (
        TokenTransaction.objects.filter(tenant=request.user)
        .order_by('-timestamp')
        .first()
    )
    token_expiry_date = last_transaction.expiry_date if last_transaction else None

    # 4 Retrieve tenant profile information.
    tenant = Tenant.objects.get(user=request.user)

    # 5 Get the current token balance from wallet (defaults to 0 if wallet is empty).
    token_balance = wallet.tokens if wallet else 0

    # 6 Fetch the five most recent token transactions for display.
    transactions = (
        TokenTransaction.objects.filter(tenant=request.user)
        .order_by('-timestamp')[:5]
    )

    # 7 Retrieve up to 20 favorite properties that are still available.
    # retrieve properties from verified landlords and whose landlords are paid and not expired
    # Subquery to get latest payment expiry for each landlord
    latest_payment_fav = Payment.objects.filter(
        landlord=OuterRef('property__landlord'),
        is_successful=True
    ).order_by('-expiry_date').values('expiry_date')[:1]

    favorites = (
        FavoriteProperty.objects.annotate(
            landlord_expiry=Subquery(latest_payment_fav, output_field=DateTimeField())
        ).filter(
            tenant=tenant,
            property__is_available=True,
            property__landlord__is_verified=True
        ).filter(
            Q(property__landlord__is_paid=True, landlord_expiry__gte=timezone.now()) | 
            Q(property__landlord__is_free_trial=True, property__landlord__trial_expiry__gte=timezone.now())
        )
        .select_related('property')  # optimize DB query
        .order_by('-added_on')[:20]
    )

    # 8 Retrieve the 20 most recently viewed available properties.
    latest_payment_views = Payment.objects.filter(
        landlord=OuterRef('property__landlord'),
        is_successful=True
    ).order_by('-expiry_date').values('expiry_date')[:1]

    recent_views = (
        PropertyView.objects.annotate(
            landlord_expiry=Subquery(latest_payment_views, output_field=DateTimeField())
        ).filter(
            tenant=tenant,
            property__is_available=True,
            property__landlord__is_verified=True
        ).filter(
            Q(property__landlord__is_paid=True, landlord_expiry__gte=timezone.now()) | 
            Q(property__landlord__is_free_trial=True, property__landlord__trial_expiry__gte=timezone.now())
        )
        .select_related('property')
        .order_by('-viewed_on')[:20]
    )

    # 9 Render the tenant dashboard template and pass all context data.
    return render(request, 'myApp/tenant_dashboard.html', {
        'tenant': tenant,
        'favorites': favorites,
        'recent_views': recent_views,
        'token_balance': token_balance,
        'token_expiry_date': token_expiry_date,
        'transactions': transactions,
        'now': timezone.now(),  # used for humanized countdown (e.g., “Expires in 3 days”)
    })



# Tenant subscription
from .forms import TenantPaymentForm
from .models import Tenant


@login_required(login_url='unified_login')
def tenant_subscription_page(request):
    tenant = get_object_or_404(Tenant, user=request.user)

    if request.method == 'POST':
        form = TenantPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.tenant = tenant  # Link payment to tenant
            payment.save()

            # Update tenant subscription
            tenant.mpesa_receipt = payment.transaction_code
            tenant.subscription_expires = timezone.now() + timedelta(days=30)
            tenant.is_subscribed = True
            tenant.save()

            messages.success(request, "Payment verified and subscription activated!")
            return redirect('tenant_dashboard')
        else:
            messages.error(request, "There was an issue with your payment submission.")
    else:
        form = TenantPaymentForm()

    context = {
        'form': form,
        'mpesa_instructions': {
            'paybill': '123456',
            'account_name': request.user.username,
            'amount': 100,
        }
    }
    return render(request, 'myApp/tenant_subscription.html', context)


# Favourites
from .models import FavoriteProperty


@login_required(login_url='unified_login')
def add_favorite(request, pk):
    tenant = request.user.tenant
    property_obj = get_object_or_404(Property, pk=pk)

    FavoriteProperty.objects.get_or_create(tenant=tenant, property=property_obj)
    return redirect('property_detail', pk=pk)

# Remove Fav
from django.views.decorators.http import require_POST


@require_POST
@login_required(login_url='unified_login')
def remove_favorite(request, pk):
    tenant = request.user.tenant
    property_obj = get_object_or_404(Property, pk=pk)

    FavoriteProperty.objects.filter(tenant=tenant, property=property_obj).delete()
    return redirect(request.META.get('HTTP_REFERER', 'tenant_dashboard'))  # return to where they came from


# Tenant payment
# views.py

@login_required(login_url='unified_login')
def tenant_mpesa_subscription(request):
    tenant = request.user.tenant

    if request.method == 'POST':
        form = TenantPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.tenant = tenant
            payment.save()

            messages.success(request, "Payment submitted. Awaiting approval.")
            return redirect('tenant_dashboard')
    else:
        form = TenantPaymentForm()

    return render(request, 'myApp/tenant_mpesa_subscription.html', {
        'form': form,
        'tenant': tenant,
        'mpesa_instructions': {
            'paybill': '247247',
            'account_name': '0430166712642',
            'amount': 100  # You may make this dynamic
        }
    })

# tenants view to update subscription
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ManualSubscriptionForm
from .models import Tenant


def manually_activate_subscription(request, tenant_id):
    tenant = get_object_or_404(Tenant, pk=tenant_id)

    if request.method == 'POST':
        form = ManualSubscriptionForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            return redirect('tenant_dashboard')  # or wherever you manage tenants
    else:
        form = ManualSubscriptionForm(instance=tenant)

    return render(request, 'myApp/manual_subscription.html', {
        'form': form,
        'tenant': tenant
    })

def terms_conditions(request):
    return render(request, 'myApp/terms_conditions.html')

# mobile views.py (Only 4)


def load_more_properties(request):
    offset = int(request.GET.get('offset', 0))
    limit = 4
    properties = Property.objects.all()[offset:offset+limit]
    
    data = {
        'properties': [
            {
                'id': prop.id,
                'url': prop.get_absolute_url(),  # Make sure your Property model has this method
                'title': prop.title,
                'rent': prop.rent,
                'city': prop.city,
                'estate': prop.estate,
                'bedrooms': prop.bedrooms,
                'bathrooms': prop.bathrooms
            }
            for prop in properties
        ]
    }
    
    return JsonResponse(data)

# Nearby houses
from math import radians, sin, cos, sqrt, atan2
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
import json
from geopy.distance import geodesic

import math
from django.db.models import Q, Subquery, DateTimeField, OuterRef
from django.views.decorators.csrf import csrf_exempt
from .models import Property, Payment  # Adjust imports as needed

@csrf_exempt
def nearby_properties_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    # 1. Parse and validate user coordinates
    try:
        data = json.loads(request.body)
        user_lat = float(data.get("latitude"))
        user_lon = float(data.get("longitude"))
        user_coord = (user_lat, user_lon)
    except (TypeError, ValueError, KeyError):
        return JsonResponse({"error": "Invalid coordinates"}, status=400)

    max_distance_km = 5.0
    now = timezone.now()

    # 2. Fast Bounding Box Calculation in SQL (~1 degree lat ~= 111km)
    # This reduces candidate properties from thousands to only those roughly in range
    lat_range = max_distance_km / 111.0
    lng_range = max_distance_km / (111.0 * math.cos(math.radians(user_lat)))

    min_lat = user_lat - lat_range
    max_lat = user_lat + lat_range
    min_lng = user_lon - lng_range
    max_lng = user_lon + lng_range

    # 3. Subquery for latest payment expiry
    latest_payment = Payment.objects.filter(
        landlord=OuterRef('landlord'),
        is_successful=True
    ).order_by('-expiry_date').values('expiry_date')[:1]

    # 4. Single optimized ORM query with Spatial DB pre-filtering
    properties = (
        Property.objects.annotate(
            landlord_expiry=Subquery(latest_payment, output_field=DateTimeField())
        )
        .filter(
            is_approved=True,
            is_available=True,
            landlord__is_verified=True,
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lng,
            longitude__lte=max_lng,
        )
        .filter(
            # Paid landlords OR Trial landlords
            Q(landlord__is_paid=True, landlord_expiry__isnull=False, landlord_expiry__gte=now)
            | Q(landlord__is_free_trial=True, landlord__trial_expiry__isnull=False, landlord__trial_expiry__gte=now)
        )
        .select_related("landlord", "property_type")
        .prefetch_related("images")[:50]  # Check max 50 spatially relevant properties
    )

    nearby = []

    # 5. High-precision Geodesic distance calculation on pre-filtered subset
    for prop in properties:
        property_coord = (prop.latitude, prop.longitude)
        distance = geodesic(user_coord, property_coord).km

        if distance <= max_distance_km:
            # Handle image fallback safely without additional DB queries
            first_image = prop.images.first()
            if first_image and first_image.image:
                image_url = first_image.image.url
            elif getattr(prop, 'image', None):
                image_url = prop.image.url
            else:
                image_url = ""

            nearby.append({
                "id": prop.id,
                "title": prop.title,
                "image_url": image_url,
                "property_type": prop.property_type.name if prop.property_type else "",
                "is_verified": prop.is_verified,
                "rent": prop.rent,
                "estate": prop.estate,
                "address": prop.address,
                "bedrooms": prop.bedrooms,
                "bathrooms": prop.bathrooms,
                "distance": round(distance, 2),
                "lat": prop.latitude,
                "lng": prop.longitude,
            })

    # Sort by closest first and return top 15 nearest properties
    nearby.sort(key=lambda x: x["distance"])
    final_results = nearby[:15]

    return JsonResponse({
        "count": len(final_results),
        "properties": final_results
    })

# Nearby vehicles start
from math import atan2, cos, radians, sin, sqrt

from myApp.models import Transporter


def nearby_vehicles_map(request):
    return render(request, "transporters/nearby_vehicles_map.html", 
                  {"GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY})

# system rating
@login_required
def rate_system(request):
    try:
        rating = SystemRating.objects.get(user=request.user)
    except SystemRating.DoesNotExist:
        rating = None

    if request.method == 'POST':
        form = SystemRatingForm(request.POST, instance=rating)
        if form.is_valid():
            new_rating = form.save(commit=False)
            new_rating.user = request.user
            new_rating.save()
            return redirect('rate_system')
    else:
        form = SystemRatingForm(instance=rating)

    all_ratings = SystemRating.objects.filter(is_approved=True)
    # average_score = all_ratings.aggregate(models.Avg('score'))['score__avg'] or 0
    average_score = all_ratings.aggregate(Avg('score'))['score__avg'] or 0


    return render(request, 'myApp/rate_system.html', {
        'form': form,
        'average_score': round(average_score, 1),
        'all_ratings': all_ratings,
    })

# myApp/views.py

from django.shortcuts import redirect, render

from .forms import BuyTokensForm
from .models import TokenTransaction, TokenWallet


@login_required
def buy_tokens(request):
    if request.method == 'POST':
        form = BuyTokensForm(request.POST)
        if form.is_valid():
            count = form.cleaned_data['token_count']
            phone = form.cleaned_data['phone_number']
            amount = count * 20  # 20 Ksh per token

            TokenTransaction.objects.create(
                tenant=request.user,
                phone_number=phone,
                tokens_bought=count,
                amount_paid=amount,
                transaction_status='Success'  # Simulated
            )

            messages.success(request, f"{count} token(s) purchased successfully.")
            return redirect('tenant_dashboard')
    else:
        form = BuyTokensForm()

    return render(request, 'myApp/buy_tokens.html', {'form': form})



@login_required
def token_history(request):
    transactions = TokenTransaction.objects.filter(tenant=request.user).order_by('-timestamp')
    return render(request, 'myApp/token_history.html', {'transactions': transactions})


from django.core.exceptions import PermissionDenied


@login_required
def tenant_comments(request, pk):
    if not hasattr(request.user, 'landlord') or request.user.landlord.pk != pk:
        raise PermissionDenied("You are not authorized to view these comments.")

    landlord = request.user.landlord

    comments = Comment.objects.filter(property__landlord=landlord)

    # Calculate average rating for each property
    property_ratings = {}
    for comment in comments:
        property_ratings.setdefault(comment.property, []).append(comment.rating)

    average_ratings = {
        prop: round(sum(ratings) / len(ratings), 1)
        for prop, ratings in property_ratings.items()
    }
    
    messages.success(request, "Your comment has been submitted successfuly! Thank You.")

    return render(request, 'myApp/property_detail.html', {
        'comments': comments,
        'average_ratings': average_ratings,
    })
  
    
def help_guide(request):
    return render(request, 'myApp/help_guide.html')

def privacy_policy(request):
    return render(request, 'myApp/privacy_policy.html')


from django.shortcuts import get_object_or_404, render

from myApp.models import SubscriptionPlan, registerUser


@login_required(login_url='login')
def landlord_subscription(request):
    landlord = get_object_or_404(registerUser, user=request.user)

    try:
        # match the user's landlord_type to the SubscriptionPlan
        subscription_plan = SubscriptionPlan.objects.get(landlord_type=landlord.landlord_type)
    except SubscriptionPlan.DoesNotExist:
        subscription_plan = None

    return render(request, 'myApp/profile.html', {'subscription_plan': subscription_plan})


def about_us(request):
    return render(request, 'myApp/about.html')

from django.shortcuts import get_object_or_404, redirect, render

from .forms import ReferralSubmissionForm
from .models import Tenant


@login_required(login_url='login')
def submit_referral(request):
    tenant = get_object_or_404(Tenant, user=request.user)

    if request.method == 'POST':
        form = ReferralSubmissionForm(request.POST, tenant=tenant)
        if form.is_valid():
            referral = form.save(commit=False)
            referral.tenant = tenant
            referral.save()
            messages.success(request, "Thank you! Your referral has been submitted.You will be rewarded in 24 hrs")
            return redirect('submit_referral')
        else:
            messages.error(request, "There was an error. Please check the form.")
    else:
        form = ReferralSubmissionForm(tenant=tenant)

    return render(request, 'myApp/submit_referral.html', {'form': form})


@login_required(login_url='login')
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if new_password == confirm_password:
            user = request.user
            if user.check_password(current_password):
                user.set_password(new_password)
                user.save()
                messages.success(request, "Your password has been changed successfully.")
                return redirect('login')
            else:
                messages.error(request, "Current password is incorrect.")
        else:
            messages.error(request, "New passwords do not match.")

    return render(request, 'myApp/change_password.html')


# Transporter Registration


from django.contrib.auth.models import User

from .forms import TransporterRegistrationForm
from .models import Transporter


def register_transporter(request):
    if request.method == "POST":
        form = TransporterRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            username = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]

            # Check if username already exists
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username is already taken.")
                return redirect("register_transporter")

            # Check if email already exists
            if User.objects.filter(email=email).exists():
                messages.error(request, "Email is already registered.")
                return redirect("register_transporter")
            
            # check if passwords match
            if password != form.cleaned_data["confirm_password"]:
                messages.error(request, "Passwords do not match.")
                return redirect("register_transporter")

            # check if emails match
            if email != form.cleaned_data["confirm_email"]:
                messages.error(request, "Emails do not match.")
                return redirect("register_transporter")

            # Create the User
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )

            # Create linked Transporter
            transporter = form.save(commit=False)
            transporter.user = user
            transporter.save()

            messages.success(request, "Transporter account created successfully. Please log in.")
            return redirect("unified_login")
    else:
        form = TransporterRegistrationForm()

    return render(request, "transporters/register_transporter.html", {
        "form": form,
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY
        })


from datetime import timedelta

from django.shortcuts import redirect, render

from .models import TransporterSubscription


@login_required
def transporter_dashboard(request):
    transporter = request.user.transporter  # One-to-one link with User

    
    # get verified transporter
    verified_transporters = Transporter.objects.filter(
        verified=True).values_list('id', flat=True)
    # --- Ratings ---
    ratings_data = TransporterRating.objects.filter(transporter=transporter).aggregate(
        avg_rating=Avg("rating"),
        total_ratings=Count("id")
    )
    avg_rating = ratings_data["avg_rating"] or 0
    total_ratings = ratings_data["total_ratings"] or 0

    now = timezone.now()
    expired = False
    expiring_soon = False
    subscription = None

    # --- Trial Check ---
    if transporter.on_trial and transporter.trial_expiry:
        if transporter.trial_expiry >= now:
            # Trial still active
            subscription = None  # No paid sub yet
            if transporter.trial_expiry <= now + timedelta(days=7):
                expiring_soon = True
        else:
            expired = True
            transporter.on_trial = False  # Auto-disable trial
            transporter.save(update_fields=["on_trial"])

    # --- Paid Subscription Check ---
    if not subscription:  # Only check if no active trial
        subscription = (
            TransporterSubscription.objects
            .filter(transporter=transporter, is_paid=True)
            .order_by("-end_date")
            .first()
        )

        if subscription and subscription.end_date:
            if subscription.end_date < now:
                expired = True
            elif subscription.end_date <= now + timedelta(days=7):
                expiring_soon = True
        else:
            # No active sub and no valid trial
            if not transporter.on_trial:
                messages.warning(request, "You do not have any active subscription or trial.")
                return redirect("mpesa:transporter_subscribe_view")

    # --- Days left ---
    days_left = None
    if subscription and subscription.end_date:
        days_left = (subscription.end_date - now).days
    elif transporter.on_trial and transporter.trial_expiry:
        days_left = (transporter.trial_expiry - now).days

    # --- Context ---
    context = {
        "transporter": transporter,
        "subscription": subscription,  # Could be None if on trial
        "expired": expired,
        "avg_rating": round(avg_rating, 1),
        "total_ratings": total_ratings,
        "expiring_soon": expiring_soon,
        "verified_transporters": verified_transporters,
        "days_left": days_left,
        "on_trial": transporter.on_trial,
        "trial_expiry": transporter.trial_expiry if transporter.on_trial else None
    }
    return render(request, "transporters/dashboard.html", context)


# Transporter edit profile
from .forms import TransporterProfileForm  # new form without username/password
from .models import Transporter
logger = logging.getLogger(__name__)

@login_required
def edit_transporter_profile(request):
    try:
        transporter = request.user.transporter
    except Transporter.DoesNotExist:
        messages.error(request, "You don't have a transporter profile yet.")
        return redirect("create_transporter_profile")

    if request.method == "POST":
        form = TransporterProfileForm(
            request.POST, 
            request.FILES, 
            instance=transporter
        )

        if form.is_valid():
            try:
                transporter = form.save(commit=False)

                # Save the instance (handles images/files)
                transporter.save()

                messages.success(request, "Your profile has been updated successfully.")
                return redirect("edit_transporter_profile")

            except Exception as e:
                # Log the full traceback
                logger.exception("Error saving transporter profile")
                messages.error(
                    request,
                    "There was an error saving your profile. Please check your inputs and try again."
                )
        else:
            # Show field-specific errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

            # Show non-field errors (model-level validation)
            for error in form.non_field_errors():
                messages.error(request, error)

    else:
        form = TransporterProfileForm(instance=transporter)

    return render(
        request, 
        "transporters/edit_profile.html", 
        {
            "form": form, 
            "transporter": transporter,
            "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
            "form_errors": form.errors if request.method == "POST" else None
        }
    )


from datetime import timedelta

from django.shortcuts import render

from .models import Transporter, TransporterSubscription


def transporter_map(request):
    now = timezone.now()
    
    # --- Collect active subscriptions (paid) ---
    active_subscriptions = TransporterSubscription.objects.filter(
        end_date__gte=now,  # not expired
        is_paid=True
    ).values_list("transporter_id", flat=True)

    # --- Collect active trials ---
    active_trials = Transporter.objects.filter(
        on_trial=True,
        trial_expiry__gte=now
    ).values_list("id", flat=True)

    # --- Combine: transporters who are online AND either subscribed OR on trial ---
    valid_ids = list(active_subscriptions) + list(active_trials)

    transporters = Transporter.objects.filter(
        online=True,
        active=True,
        # verified=True,
        id__in=valid_ids
    )

    # --- Distinct cities (exclude empty) ---
    cities = (
        Transporter.objects.exclude(city__isnull=True).exclude(city__exact="")
        .values_list("city", flat=True).distinct().order_by("city")
    )

    # --- Distinct vehicle types ---
    vehicle_types = (
        Transporter.objects.values_list("transport_type", flat=True)
        .distinct()
        .order_by("transport_type")
    )

    # --- Build JSON for map markers ---
    data = []
    for t in transporters:
        data.append({
            "id": t.id,
            "full_name": t.full_name,
            "transport_type": t.get_transport_type_display(),
            "phone": t.phone,
            "vehicle_capacity": t.vehicle_capacity,
            "city": t.city,
            "vehicle_plate": t.vehicle_plate,
            "vehicle_image": t.vehicle_image.url if t.vehicle_image else None,
            "is_available": t.is_available,
            "description": t.description,
            "verified": t.verified,
            "latitude": t.latitude,
            "longitude": t.longitude,
            "online": t.online,
            "on_trial": t.on_trial,  # helpful for frontend labels
            "trial_expiry": t.trial_expiry.strftime("%Y-%m-%d") if t.trial_expiry else None
        })

    return render(request, "transporters/transporters_map.html", {
        "transporters_json": json.dumps(data),
        "vehicle_types": vehicle_types,
        "transporters": transporters,
        "cities": cities,
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY
    })



# Transporter details
# @login_required(login_url='unified_login')
from django.db.models import Avg, Count

from .models import Transporter, TransporterRating


def transporter_details(request, transporter_id):
    transporter = get_object_or_404(Transporter, id=transporter_id)

    # Get average rating and count
    ratings_data = TransporterRating.objects.filter(transporter=transporter).aggregate(
        avg_rating=Avg("rating"),
        total_ratings=Count("id")
    )

    avg_rating = ratings_data["avg_rating"] or 0
    total_ratings = ratings_data["total_ratings"] or 0

    context = {
        "transporter": transporter,
        "avg_rating": avg_rating,
        "total_ratings": total_ratings,
    }
    return render(request, "transporters/transporter_details.html", context)


def vehicle_filters(request):
    vehicle_type = request.GET.get('vehicle_type', '').strip()
    transporters = []

    if vehicle_type:
        # Filter transporters by vehicle type
        transporters = Transporter.objects.filter(
            transport_type__iexact=vehicle_type,
            online=True
        )

    return render(request, "transporters/transporters_map.html", {
        "transporters": transporters
    })


from django.db.models import Q
from django.shortcuts import render

from .models import Property, Transporter


@login_required
def search(request):
    query = request.GET.get('q', '').strip()
    properties = []
    transporters = []
    cities = []

    if query:
        # Search properties by city
        properties = Property.objects.filter(
            Q(city__icontains=query),
            is_approved=True,
            is_available=True
        )

        # One unified transporter query
        transporters = Transporter.objects.filter(
            Q(transport_type__icontains=query) |
            Q(vehicle_name__icontains=query) |
            Q(city__icontains=query),
            online=True,
            is_approved=True,
            is_available=True
        ).distinct()

        # Cities are derived from those same transporters (not a new query)
        cities = transporters.values_list('city', flat=True).distinct()

    return render(request, 'myApp/search_results.html', {
        'query': query,
        'properties': properties,
        'transporters': transporters,
        'cities': cities
    })


from django.db.models import Sum
# views.py
from django.shortcuts import redirect, render

from .models import TransporterEarnings, TransporterSubscription


# Transporter payment history
@login_required
def payment_history_list(request):
    # Full payment history (successful only)
    history = TransporterSubscription.objects.filter(
        transporter__user=request.user,is_paid=True
    ).order_by("-is_paid", "-start_date")
    
    # Failed payments
    failed_payments = TransporterSubscription.objects.filter(
        transporter__user=request.user,
        is_paid=False
    ).order_by("-start_date")
    
    # transporter earnings
    earnings = TransporterEarnings.objects.filter( 
                transporter__user=request.user,is_paid=True
            ).order_by("-is_paid", "-created_at")
    
    # Total transporter earnings
    total_earnings = earnings.filter(is_paid=True).aggregate(total=Sum("earned_amount"))["total"] or 0
    
    
    # Total failed payments
    failed_count = failed_payments.count()

    # Total successful payments
    total_successful_payments = history.filter(is_paid=True).count()

    # Total spent
    total_spent = history.filter(is_paid=True).aggregate(total=Sum("amount"))["total"] or 0

    # Active subscriptions
    active_subscriptions = history.filter(
        is_paid=True,
        end_date__gte=timezone.now()
    ).count()
    
    

    context = {
        "history": history,
        "failed_payments": failed_payments,
        "failed_count": failed_count,
        "total_successful_payments": total_successful_payments,
        "total_spent": total_spent,
        "active_subscriptions": active_subscriptions,
        "total_earnings":total_earnings
    }
    return render(request, "transporters/payment_history_list.html", context)

# transporter rating
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TransporterRatingForm
from .models import Transporter, TransporterRating


@login_required(login_url="unified_login")
def rate_transporter(request, transporter_id):
    transporter = get_object_or_404(Transporter, id=transporter_id)

    existing_rating = TransporterRating.objects.filter(transporter=transporter, user=request.user).first()
    if request.method == "POST":
        form = TransporterRatingForm(request.POST, instance=existing_rating)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.transporter = transporter
            rating.user = request.user
            rating.save()
            messages.success(request, "Your rating has been submitted successfully.")
            return redirect("transporter_details", transporter_id=transporter.id)
    else:
        form = TransporterRatingForm(instance=existing_rating)


        context = {
            "form": form,
            "transporter": transporter,
        }
    return render(request, "transporters/rate_transporter.html", context)

from django.db.models import Avg, Count


def all_transporter_ratings(request, transporter_id):
    transporter = get_object_or_404(Transporter, id=transporter_id)

    # Fetch ratings
    ratings = TransporterRating.objects.filter(transporter=transporter).order_by("-created_at")

    # Average + total
    ratings_data = ratings.aggregate(
        avg_rating=Avg("rating"),
        total_ratings=Count("id")
    )
    avg_rating = ratings_data["avg_rating"] or 0
    total_ratings = ratings_data["total_ratings"] or 0

    # Distribution (1–5 stars)
    distribution = ratings.values("rating").annotate(count=Count("id"))
    rating_distribution = {i: 0 for i in range(1, 6)}
    for entry in distribution:
        rating_distribution[entry["rating"]] = entry["count"]

    context = {
        "transporter": transporter,
        "ratings": ratings,
        "avg_rating": round(avg_rating, 1),
        "total_ratings": total_ratings,
        "rating_distribution": rating_distribution,
    }
    return render(request, "transporters/all_transporter_ratings.html", context)

# Transporter earnings
from .forms import TransporterEarningsForm
from .models import TransporterEarnings


from mpesa.models import MoversPlan
@login_required(login_url="unified_login")
def mover_pricing(request):
    plans = MoversPlan.objects.all().order_by('price')
    context = {
        "plans": plans
    }
    return render(request, "transporters/mover_pricing.html", context)

@login_required(login_url="unified_login")
def add_transporter_earnings(request):
    if request.method == "POST":
        form = TransporterEarningsForm(request.POST)
        if form.is_valid():
            earning = form.save(commit=False)
            earning.transporter = request.user.transporter  # assumes OneToOneField User -> Transporter
            earning.save()
            messages.success(request, "Earning record added successfully.")
            return redirect("transporter_earnings_list")  # change to your earnings list URL
    else:
        form = TransporterEarningsForm()

    return render(request, "transporters/add_earnings.html", {"form": form})


import calendar

from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractYear
# Fetch all transporter earnings
from django.shortcuts import render

from .models import TransporterEarnings


@login_required(login_url="unified_login")
def transporter_earnings_list(request):
    transporter = getattr(request.user, "transporter", None)

    if not transporter:
        return render(request, "transporters/earnings_list.html", {
            "earnings": [],
            "total_earned": 0,
            "data_by_year": "{}"
        })

    # Fetch all earnings
    earnings = TransporterEarnings.objects.filter(
        transporter=transporter
    ).order_by("-created_at")

    # Total earnings
    total_earned = earnings.aggregate(total=Sum("earned_amount"))["total"] or 0

    # Monthly totals grouped by year
    monthly = (
        earnings.annotate(year=ExtractYear("created_at"), month=ExtractMonth("created_at"))
        .values("year", "month")
        .annotate(total=Sum("earned_amount"))
        .order_by("year", "month")
    )

    # Organize into year → months/totals dict
    data_by_year = {}
    for m in monthly:
        year = m["year"]
        month_label = calendar.month_abbr[m["month"]]  # Jan, Feb, etc.
        if year not in data_by_year:
            data_by_year[year] = {"labels": [], "totals": []}
        data_by_year[year]["labels"].append(month_label)
        data_by_year[year]["totals"].append(float(m["total"]))  # Ensure JSON serializable

    context = {
        "earnings": earnings,
        "total_earned": float(total_earned),
        "data_by_year": json.dumps(data_by_year),  # pass as JSON for Chart.js
    }

    return render(request, "transporters/earnings_list.html", context)

# FAQs view
from django.shortcuts import redirect, render
from .forms import FAQForm
from .models import FAQ

# List all FAQs (public view)
def faq_list(request):
    faqs = FAQ.objects.all()
    return render(request, "faq/faq_list.html", {"faqs": faqs})

# Admin/Landlord: Add new FAQ
@login_required
def add_faq(request):
    if request.method == "POST":
        form = FAQForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("faq_list")  # Redirect to FAQ list after saving
    else:
        form = FAQForm()
    return render(request, "faq/add_faq.html", {"form": form})

# AI agent

def chat_page(request):
   return render(request, 'Agent/chat.html')

import json
import random

from django.db.models import Q, OuterRef, Subquery, DateTimeField
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Property, Payment, GeneralTip

# ============================================================
# CHANGELOG (read this before diffing against the original)
# ============================================================
# FIXED:
#   1. Rent parsing (`below 30k` returning zero results despite matching
#      properties) was NOT the actual cause you hit — that regex worked
#      correctly in isolation. Verified separately.
#   2. REAL gug: bedroom/bathroom filters used `str(num) in lower_msg`,
#      a bare substring check. "rent below 30k" contains the digit "0"
#      and "3" as substrings, so if 0 or 3 existed as a stored bedrooms/
#      bathrooms value, the code silently added bedrooms=0/bathrooms=0
#      (or =3) to the query -- collapsing results to studios only, with
#      no trace of why. Fixed by requiring the digit to be adjacent to
#      an actual unit word ("bedroom", "bed", "bathroom", "bath") via
#      regex with word boundaries, not bare substring containment.
#   3. Rent clause parsing only ever applied ONE filter (if/elif chain)
#      and, worse, picked whichever clause the regex happened to reach
#      first when scanning left-to-right -- not the first clause in the
#      sentence, and not any clause chosen by policy. When a message
#      contains multiple rent phrases, this version now finds ALL of
#      them and applies the LAST one mentioned (see ASSUMPTION above
#      this file). If you want different behavior (narrowest range,
#      or ask-for-clarification instead of guessing), tell me and I'll
#      change the resolution policy -- the parsing/collection part
#      doesn't need to change either way.
#   4. Removed a dangling, unreachable module-level code block (the
#      `latest_payment = Payment.objects.filter(...)` fragment that sat
#      outside any function, referencing OuterRef/DateTimeField/timezone
#      that weren't imported in the original file). If that was really
#      sitting at module scope on disk, it would have crashed Django at
#      import time. Its logic already exists correctly inside the view.
#   5. Chat results and rental tips are now served entirely from the
#      property and GeneralTip database records.
#
# Existing endpoint note: `@csrf_exempt` is retained from the current
# chat integration; no session history is stored by the database search.
# ============================================================

# --- Number word mapping for bedrooms (1-10) ---
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def extract_bedroom_count(text, room_type="bedroom"):
    text = text.lower().strip()

    if match := re.search(rf"\b(\d+)\s*{room_type}s?\b", text):
        return int(match.group(1))

    for word, num in NUMBER_WORDS.items():
        pattern = re.compile(rf"\b{word}\s*{room_type}s?\b", re.IGNORECASE)
        if pattern.search(text):
            return num

    return None


# --- Global amenity keywords (unchanged from your original list) ---
AMENITY_KEYWORDS = [
    "flooring", "cement screed flooring", "vinyl flooring", "marble flooring",
    "wood floor", "natural wood flooring", "tiles", "tile floor",
    "ceiling", "gypsum ceiling", "pop ceiling", "pvc ceiling", "wooden ceiling",
    "acoustic ceiling", "metal ceiling", "coffered ceiling", "ceiling fan",
    "curtain rods", "fitted cabinets", "wall mirrors",
    "natural lighting", "sliding windows", "sliding doors",
    "double glazed windows", "soundproof", "balcony", "balcony view",
    "terrace", "rooftop", "rooftop terrace", "driveway", "paved compound",
    "garden", "outdoor sitting area", "perimeter lighting",
    "storage", "storage room", "garage", "parking", "open parking", "covered parking",
    "servant quarters", "guest cloakroom", "ensuite bathroom", "shared bathroom",
    "shared toilet", "office", "home office", "walk-in closet",
    "wardrobe", "built-in wardrobes", "tv wall", "library",
    "jacuzzi", "hot tub", "steam room", "bathtub", "shower cubicle",
    "hot shower", "squat toilet", "sitting toilet", "anti-slip tiles",
    "anti-slip tiles in wet areas", "heated water system",
    "kitchen", "open plan kitchen", "modern kitchen", "countertop kitchen",
    "pantry", "breakfast bar", "single sink", "double sink",
    "dishwasher", "dishwashing machine", "kitchen appliances",
    "built-in appliances", "energy-efficient appliances", "kitchen cabinets",
    "built-in kitchen appliances", "refrigerator space", "chimney",
    "laundry", "laundry room", "laundry drying area", "washing machine",
    "in-unit laundry", "in-unit laundry machine", "ironing station",
    "cleaning services",
    "solar", "solar panel system", "solar backup", "generator", "generator backup",
    "generator power backup", "water backup", "reliable water supply",
    "borehole water", "rooftop water tank", "water pressure boosters",
    "greywater recycling", "greywater recycling system",
    "rainwater harvesting", "sun-powered hot water",
    "sun-powered hot water system", "wastewater treatment",
    "wastewater treatment system", "electricity-prepaid",
    "electricity-postpaid", "electricity tokens",
    "recycling", "recycling center", "recycling pickup",
    "composting facility", "energy-efficient",
    "dstv", "satellite dish", "satellite dish installation ready",
    "tv points", "wall-mounted tv", "wall-mounted tv points",
    "cable tv", "cable tv ready", "wifi", "fiber", "fiber internet ready",
    "internet", "smart lighting", "home automation",
    "home automation system", "smart thermostat", "water leak sensors",
    "smart water leak sensors", "smart home", "smart doorbell",
    "video doorbell", "smart lock",
    "furnished", "fully furnished", "outdoor grilling", "outdoor grilling spot",
    "bbq", "barbecue", "gym", "swimming pool", "pool",
    "jogging track", "children play area", "kids play area",
    "game room", "restaurant", "daycare", "shared kitchen",
    "study area", "shared study", "shared study area", "event space",
    "meeting space", "shared event space", "reception desk",
    "visitor parking", "support staff", "resident staff",
    "resident support staff available", "pet-friendly", "pet-friendly areas",
    "elevator", "lift",
    "fireplace", "underfloor heating", "air conditioning", "ac", "cooling",
    "soundproof walls", "soundproof windows",
    "smart lock", "smart doorbell", "video doorbell", "intercom",
    "intercom system", "rfid", "keycard access", "rfid / keycard access",
    "biometric access", "motion sensor", "motion sensor lighting",
    "security lighting", "boom gate", "double gate", "double gate system",
    "guard dogs", "guard house", "security patrols", "security guard",
    "visitor management", "visitor management system",
    "alarm", "security alarm", "security alarm system",
    "cctv", "24/7 cctv", "24/7 cctv surveillance", "gated community",
    "perimeter wall", "electric fence",
    "fire hose", "fire hose reels", "sprinkler system",
    "smoke detectors", "carbon monoxide detectors", "fire extinguishers",
    "emergency alert", "emergency alert system", "emergency stairwell",
    "fire exit", "fire exit/emergency stairwell", "assembly point",
    "emergency assembly point",
    "disabled access", "wheelchair accessible",
]


# --- Rental Tip Generator with Human Touch ---
# --- Human Response Formatter ---
def format_human_response(properties_data, show_search_status=False):
    count = len(properties_data)
    if count == 1:
        return "I found 1 rental that matches your search."
    if count:
        return f"Here are {count} rentals that match your search."
    if show_search_status:
        return "I couldn't find rentals matching those details. Try another area or a wider rent range."
    return "Tell me the area, rent range, or home type you want to find."


# --- Helper: normalize shorthand numbers like "20k" -> 20000 ---
def normalize_number(text):
    if not text:
        return None
    text = text.lower().replace(",", "").strip()
    text = re.sub(r"^(?:ksh|kes)\.?\s*", "", text)
    multiplier = 1
    suffix = re.search(r"\s*(k|thousand|m|million)$", text)
    if suffix:
        multiplier = 1_000_000 if suffix.group(1) in {"m", "million"} else 1_000
        text = text[:suffix.start()].strip()
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


# --- FIX: rent clause extraction -----------------------------------------
# Finds every rent clause in the message (between/below/above/around),
# in the order they appear, and returns a single resolved filter using
# LAST-MENTIONED-WINS. See ASSUMPTION note at top of this file for why.
def extract_rent_filter(lower_msg):
    candidates = []  # (start_index, kind, value_or_tuple)
    lower_msg = lower_msg.replace(":", " ").replace("=", " ")

    amount = r"(?:(?:ksh|kes)\.?\s*)?(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:k|thousand|m|million)?"
    range_pattern = re.compile(
        rf"(?:(?P<prefix>\b(?:rent|budget|price)\b(?:\s+(?:range|of|is))?\s+)?"
        rf"(?P<range_word>between|from)\s+)?"
        rf"(?P<low>{amount})\s*(?:to|and|[-–—])\s*(?P<high>{amount})"
    )
    range_spans = []
    rent_context = re.compile(r"\b(?:rent|budget|price|between|from)\b|\b(?:ksh|kes)\b|\d\s*(?:k|thousand|m|million)\b")
    for match in range_pattern.finditer(lower_msg):
        if re.match(r"\s*(?:bedrooms?|beds?|bathrooms?|baths?|rooms?)\b", lower_msg[match.end():]):
            continue
        before = lower_msg[max(0, match.start() - 32):match.start()]
        marked_range = bool(match.group("prefix") or match.group("range_word") or rent_context.search(before))
        marked_range = marked_range or bool(re.search(r"(?:k|thousand|m|million)\s*$|\b(?:ksh|kes)\b", match.group("low")))
        marked_range = marked_range or bool(re.search(r"(?:k|thousand|m|million)\b", match.group("high")))
        if not marked_range:
            continue
        raw_low, raw_high = match.group("low"), match.group("high")
        min_rent = normalize_number(raw_low)
        max_rent = normalize_number(raw_high)
        suffix_factors = {"k": 1_000, "thousand": 1_000, "m": 1_000_000, "million": 1_000_000}
        low_suffix = re.search(r"\s*(k|thousand|m|million)\s*$", raw_low)
        high_suffix = re.search(r"\s*(k|thousand|m|million)\s*$", raw_high)
        # In shorthand ranges, carry the stated unit across both bounds:
        # “30 to 50k” means “30k to 50k”, and “1 to 1.5m” means millions.
        if low_suffix and not high_suffix and max_rent is not None and max_rent < 1_000:
            max_rent *= suffix_factors[low_suffix.group(1)]
        elif high_suffix and not low_suffix and min_rent is not None and min_rent < 1_000:
            min_rent *= suffix_factors[high_suffix.group(1)]
        if min_rent is not None and max_rent is not None:
            range_spans.append(match.span())
            candidates.append((match.start(), "between", (min_rent, max_rent)))

    # Ignore one-sided words that occur inside a two-sided range, e.g. the
    # “from 30” in “rent from 30 to 50k”.
    single_patterns = [
        ("below", rf"\b(?:below|under|less than|not more than|no more than|up to|at most|maximum(?: budget| rent| price)?(?: of| is)?|max(?:imum)?(?: budget| rent| price)?(?: of| is)?|budget\s+(?:max(?:imum)?|up to)|within(?: budget(?: of| is)?)?)\s+(?P<amount>{amount})"),
        ("above", rf"\b(?:above|over|greater than|more than|no less than|not less than|at least|minimum(?: budget| rent| price)?(?: of| is)?|min(?:imum)?(?: of| is)?|starting (?:at|from)|from)\s+(?P<amount>{amount})"),
        ("around", rf"\b(?:exactly|around|about|approximately|roughly|near|close to)\s+(?P<amount>{amount})"),
    ]
    for kind, pattern in single_patterns:
        for match in re.finditer(pattern, lower_msg):
            if any(match.start() < end and match.end() > start for start, end in range_spans):
                continue
            if re.match(r"\s*(?:bedrooms?|beds?|bathrooms?|baths?|rooms?)\b", lower_msg[match.end():]):
                continue
            value = normalize_number(match.group("amount"))
            if value is not None:
                candidates.append((match.start(), kind, value))

    # A stated budget or target rent without a comparator means a target
    # price, represented as a ±15% band. Explicit range/comparator spans above
    # take precedence and prevent this pattern from duplicating their amount.
    target_pattern = re.compile(
        rf"\b(?:rent|price|budget)\s+(?:of|is|around|about|up to|max(?:imum)?|)?\s*(?P<amount>{amount})"
    )
    for match in target_pattern.finditer(lower_msg):
        if any(match.start() < end and match.end() > start for start, end in range_spans):
            continue
        if re.match(r"\s*(?:to|and|[-–—])\s*" + amount, lower_msg[match.end():]):
            continue
        value = normalize_number(match.group("amount"))
        if value is not None:
            prefix = lower_msg[max(0, match.start() - 28):match.start()]
            is_explicit_cap = bool(re.search(r"\b(?:up to|max(?:imum)?|under|below|less than|not more than|no more than|at most|within(?: my)?)\s*$", prefix))
            is_explicit_cap = is_explicit_cap or bool(re.search(r"\b(?:up to|max(?:imum)?)\b", match.group(0)))
            kind = "below" if is_explicit_cap else "budget" if re.search(r"\bbudget\b", match.group(0)) else "around"
            candidates.append((match.start(), kind, value))

    # Also accept the common reversed form “14k budget” / “KES 14,000 rent
    # budget”, where the amount comes before the budget keyword.
    reverse_budget_pattern = re.compile(
        rf"(?P<amount>{amount})\s+(?:(?:monthly|rental|rent)\s+)?budget\b"
    )
    for match in reverse_budget_pattern.finditer(lower_msg):
        if any(match.start() < end and match.end() > start for start, end in range_spans):
            continue
        value = normalize_number(match.group("amount"))
        if value is not None:
            candidates.append((match.start(), "budget", value))

    if not candidates:
        return None

    # Last-mentioned rent clause wins, matching corrections like “actually,
    # make it KES 30,000”.
    candidates.sort(key=lambda c: c[0])
    return candidates[-1][1], candidates[-1][2]


def apply_rent_filter(qs, lower_msg, context_info):
    resolved = extract_rent_filter(lower_msg)
    if not resolved:
        return qs

    kind, value = resolved
    if kind == "between":
        min_rent, max_rent = value
        if min_rent > max_rent:
            min_rent, max_rent = max_rent, min_rent
        qs = qs.filter(rent__gte=min_rent, rent__lte=max_rent)
        context_info.append(f"rent between KES {min_rent:,} and KES {max_rent:,}")
    elif kind == "below":
        qs = qs.filter(rent__lte=value)
        context_info.append(f"rent up to KES {value:,}")
    elif kind == "above":
        qs = qs.filter(rent__gte=value)
        context_info.append(f"rent at least KES {value:,}")
    elif kind == "budget":
        lower_bound = max(0, value - 5_000)
        upper_bound = value + 5_000
        qs = qs.filter(rent__gte=lower_bound, rent__lte=upper_bound)
        context_info.append(f"rent within KES {lower_bound:,}–{upper_bound:,} of the KES {value:,} budget")
    elif kind == "around":
        lower_bound = int(value * 0.85)
        upper_bound = int(value * 1.15)
        qs = qs.filter(rent__gte=lower_bound, rent__lte=upper_bound)
        context_info.append(f"rent around KES {value:,} (\u00b115%)")

    return qs


def build_agent_property_context(property_obj):
    """Build the listing details and review summary shown in chat."""
    ratings = property_obj.ratings.all()
    low_rating_reviews = [
        {"stars": score, "text": review.strip()[:350]}
        for score, review in ratings.filter(score__lte=2)
        .exclude(review__isnull=True).exclude(review__exact="")
        .order_by("-timestamp").values_list("score", "review")[:3]
    ]
    recent_rating_reviews = [
        {"stars": score, "text": review.strip()[:350]}
        for score, review in ratings.exclude(review__isnull=True).exclude(review__exact="")
        .order_by("-timestamp").values_list("score", "review")[:5]
    ]
    approved_comments = [
        comment.strip()[:350]
        for comment in property_obj.comments.filter(is_approved=True)
        .exclude(content__exact="").order_by("-timestamp")
        .values_list("content", flat=True)[:5]
    ]
    average_rating = ratings.aggregate(average=Avg("score"))["average"]
    return {
        "id": property_obj.id,
        "title": property_obj.title,
        "is_verified": property_obj.is_verified,
        "rent_kes": str(property_obj.rent),
        "city": property_obj.city,
        "estate": property_obj.estate,
        "bedrooms": property_obj.bedrooms,
        "bathrooms": property_obj.bathrooms,
        "property_amenities": list(property_obj.amenities.values_list("name", flat=True)[:5]),
        "rating_count": ratings.count(),
        "average_rating": round(average_rating, 1) if average_rating is not None else None,
        "low_rating_count": ratings.filter(score__lte=2).count(),
        "low_rating_reviews": low_rating_reviews,
        "recent_rating_reviews": recent_rating_reviews,
        "recent_approved_comments": approved_comments,
    }


# --- FIX: bedroom/bathroom extraction ------------------------------------
# Original bug: `str(num) in lower_msg` is a bare substring check, so any
# digit anywhere in the message (a rent figure, an estate name, etc.) could
# match a stored bedrooms/bathrooms value and silently over-filter. This
# version requires the digit to be directly adjacent to a real unit word.
def extract_room_count(lower_msg, distinct_values, unit_words):
    unit_pattern = "|".join(unit_words)
    match = re.search(rf"\b(\d+)\s*(?:{unit_pattern})s?\b", lower_msg)
    if match:
        num = int(match.group(1))
        if num in distinct_values:
            return num
    return None


BEDROOM_WORD_COUNTS = {
    "bedsitter": 0,
    "single room": 0,
    "studio": 0,
    "one bedroom": 1,
    "two bedroom": 2,
    "three bedroom": 3,
    "four bedroom": 4,
    "five bedroom": 5,
    "six bedroom": 6
}


def extract_bedroom_word_count(lower_msg):
    for phrase, num in BEDROOM_WORD_COUNTS.items():
        if re.search(rf"\b{re.escape(phrase)}\b", lower_msg):
            return num
    return None


# --- Main AI Agent View ---
@csrf_exempt
def ai_agent(request):
    if request.method == "GET":
        return JsonResponse({"reply": "Tell me the area, rent range, or home type you want to find."})

    if request.method != "POST":
        return JsonResponse({"error": "Oops, something went wrong! Try again."}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
        if not user_message:
            return JsonResponse({"reply": "I'd love to help! What are you looking for in a rental?"})

        # --- Base availability + active-subscription filter ---
        qs = Property.objects.filter(is_available=True, is_approved=True)
        latest_payment = Payment.objects.filter(
            landlord=OuterRef("landlord"), is_successful=True
        ).order_by("-expiry_date").values("expiry_date")[:1]

        qs = qs.annotate(
            landlord_expiry=Subquery(latest_payment, output_field=DateTimeField())
        ).filter(
            Q(landlord__is_paid=True, landlord__is_verified=True, landlord_expiry__gte=timezone.now())
            | Q(landlord__is_free_trial=True, landlord__is_verified=True, landlord__trial_expiry__gte=timezone.now())
        )

        context_info = []
        lower_msg = user_message.lower()

        # Match every city represented by a listing, not a fixed city list.
        known_cities = sorted(
            {city.strip() for city in Property.objects.values_list("city", flat=True) if city and city.strip()},
            key=len,
            reverse=True,
        )
        for city in known_cities:
            if re.search(rf"(?<![a-z0-9]){re.escape(city.lower())}(?![a-z0-9])", lower_msg):
                qs = qs.filter(city__icontains=city)
                context_info.append(f"city: {city}")
                break

        # --- Property Type Filter ---
        PROPERTY_TYPE_SYNONYMS = {
            "apartment": [
                "flat", "flats", "apartment", "apartments", "rental apartment",
                "apartment house", "block", "rental flat", "unit", "apartment unit",
                "bedsitter apartment", "studio apartment",
            ],
            "townhouse": [
                "town house", "town-home", "town home", "row house", "terraced house",
                "terrace home", "townhomes", "townhouses", "duplex", "duplex house",
                "mews", "linked house",
            ],
            "villa": [
                "maisonette", "villas", "villa house", "luxury house", "holiday home",
                "standalone house", "executive villa", "private villa", "detached house",
                "family villa",
            ],
            "bungalow": [
                "bungalows", "bungalow house", "one-storey house", "single storey",
                "ground floor house",
            ],
            "hostel": [
                "hostels", "student hostel", "student housing", "campus hostel",
                "university hostel", "college hostel", "boarding house", "dorm",
                "dormitory", "student residence",
            ],
            "condo": [
                "condominium", "condominiums", "condos", "condo unit",
                "serviced apartment", "furnished condo", "executive condo",
            ],
            "single room": [
                "single", "one room", "single bedsitter",
                "small room", "single house", "1 room", "room to let", "room for rent",
                "rental room", "simple room",
            ],
            "double room": [
                "two room", "2 room", "double", "double rooms", "double bedsitter",
                "two-bedroom bedsitter", "spacious room", "big room",
            ],
            "bedsitter": [
                "bed sitter", "bed-sitter", "studio", "studio room", "studio flat",
                "studio bedsitter", "open plan room", "self-contained room",
                "self contained", "bedsit", "bedsitters", "bachelor pad",
            ],
        }

        for canonical_type, synonyms in PROPERTY_TYPE_SYNONYMS.items():
            matched = False
            for synonym in synonyms:
                if re.search(rf"\b{re.escape(synonym)}\b", lower_msg):
                    qs = qs.filter(property_type__name__icontains=canonical_type)
                    context_info.append(f"type: {canonical_type}")
                    matched = True
                    break
            if matched:
                break

        if not any("type:" in info for info in context_info):
            if match := re.search(
                r"\b(villa|maisonette|apartment|cottage|townhouse|bungalow|hostel|condo|single room|double room|bedsitter|bed sitter)\b",
                lower_msg,
            ):
                qs = qs.filter(property_type__name__icontains=match.group(1))
                context_info.append(f"type: {match.group(1)}")

        # --- Estate filter (dynamic) ---
        estates = Property.objects.values_list("estate", flat=True).distinct()
        for est in estates:
            if est and re.search(rf"\b{re.escape(est.lower())}\b", lower_msg):
                qs = qs.filter(estate__icontains=est)
                context_info.append(f"estate: {est}")
                break

        # --- Bathrooms filter (FIXED: word-boundary, unit-word required) ---
        bathroom_numbers = list(Property.objects.values_list("bathrooms", flat=True).distinct())
        bath_num = extract_room_count(lower_msg, bathroom_numbers, ["bathroom", "bathrooms", "bath", "ba"])
        if bath_num is not None:
            qs = qs.filter(bathrooms=bath_num)
            context_info.append(f"bathrooms: {bath_num}")

        # --- Bedrooms filter (FIXED: word-boundary, unit-word required) ---
        bedroom_numbers = list(Property.objects.values_list("bedrooms", flat=True).distinct())
        bed_num = extract_room_count(lower_msg, bedroom_numbers, ["bedroom", "bedrooms", "bed", "beds"])
        if bed_num is None:
            bed_num = extract_bedroom_word_count(lower_msg)
        if bed_num is not None:
            qs = qs.filter(bedrooms=bed_num)
            context_info.append(f"bedrooms: {bed_num}")

        # --- Rent filter (FIXED: collects all clauses, resolves last-mentioned-wins) ---
        qs = apply_rent_filter(qs, lower_msg, context_info)

        # Balcony or balconies
        if re.search(r"\bbalcon(?:y|ies)\b", lower_msg):
            qs = qs.filter(has_balcony=True)
            context_info.append("has balcony")

        # Verified property
        if re.search(r"\bverified\b", lower_msg):
            qs = qs.filter(is_verified=True)
            context_info.append("is verified")

        # Featured property
        if re.search(r"\bfeatured\b", lower_msg):
            qs = qs.filter(featured=True)
            context_info.append("featured")

        # Amenities
        amenity_terms = {term.lower().strip() for term in AMENITY_KEYWORDS}
        amenity_terms.update(
            term.lower().strip() for term in Amenity.objects.values_list("name", flat=True)
            if term and term.strip()
        )
        matched_amenity_terms = sorted(
            (
                term for term in amenity_terms
                if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower_msg)
            ),
            key=len,
            reverse=True,
        )
        # Avoid applying a short alias such as “parking” as a second filter
        # when the user explicitly asked for a more specific “covered parking”.
        amenities = []
        for term in matched_amenity_terms:
            if any(
                term != chosen and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", chosen)
                for chosen in amenities
            ):
                continue
            amenities.append(term)
        social_terms = {
            "school", "schools", "kindergarten", "university", "college",
            "hospital", "hospitals", "clinic", "clinics", "pharmacy", "pharmacies",
            "supermarket", "supermarkets", "market", "markets", "mall", "malls",
            "bank", "banks", "atm", "restaurant", "restaurants", "cafe", "cafes",
            "park", "parks", "playground", "playgrounds", "bus stop", "bus stops",
            "bus station", "bus stations", "church", "churches", "mosque", "mosques",
            "library", "libraries", "community centre", "community centers",
        }
        nearby_relation = bool(re.search(
            r"\b(?:near(?:by)?|close to|walking distance(?: of| to)?|within\s+\d+\s*(?:m|km)?\s+of)\b",
            lower_msg,
        ))
        social_terms_requested = [
            term for term in social_terms
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower_msg)
        ]
        if nearby_relation and social_terms_requested:
            amenities = [term for term in amenities if term not in social_terms]
            context_info.append(
                "nearby facilities requested (distance data unavailable): "
                + ", ".join(sorted(social_terms_requested))
            )
        for amenity in amenities:
            qs = qs.filter(amenities__name__icontains=amenity)
        if amenities:
            context_info.append(f"amenities: {', '.join(amenities)}")

        # Only return listings for a real property search. Otherwise the
        # unfiltered queryset would make greetings and general questions show
        # the first properties in the database.
        mentions_property = re.search(
            r"\b(house|home|property|properties|apartment|flat|room|bedsitter|"
            r"villa|rental|rentals|place|listing|listings)\b",
            lower_msg,
        )
        asks_to_search = re.search(
            r"\b(find|show|search|look(?:ing)? for|recommend|suggest|available)\b",
            lower_msg,
        )
        is_property_search = (
            bool(context_info)
            or bool(mentions_property and asks_to_search)
            or bool(nearby_relation and social_terms_requested)
        )
        matched_properties = (
            list(qs.select_related("property_type").prefetch_related("amenities")[:5])
            if is_property_search else []
        )
        tip_pool = list(GeneralTip.objects.exclude(tip="").values_list("tip", flat=True))
        properties_data = []
        for property_obj in matched_properties:
            image_list = [image.image.url for image in property_obj.images.all()]
            review_data = build_agent_property_context(property_obj)
            rating_count = review_data["rating_count"]
            average_rating = review_data["average_rating"]
            review_summary = (
                f"{average_rating}/5 from {rating_count} ratings"
                if rating_count and average_rating is not None else ""
            )
            properties_data.append({
                "id": property_obj.id,
                "title": property_obj.title,
                "is_verified": review_data["is_verified"],
                "rent": str(property_obj.rent),
                "city": property_obj.city,
                "estate": property_obj.estate,
                "bedrooms": property_obj.bedrooms,
                "bathrooms": property_obj.bathrooms,
                "has_balcony": property_obj.has_balcony,
                "amenities": [amenity.name for amenity in property_obj.amenities.all()[:5]],
                "image_url": image_list[0] if image_list else "",
                "images": image_list,
                "review_summary": review_summary,
                "low_rating_reviews": [item["text"] for item in review_data["low_rating_reviews"]],
                "review_comments": review_data["recent_approved_comments"][:2],
            })

        human_reply = format_human_response(properties_data, show_search_status=is_property_search)
        return JsonResponse({
            "reply": human_reply,
            "properties": properties_data,
            "tip": random.choice(tip_pool) if tip_pool else "",
        })

    except Exception as e:
        return JsonResponse({
            "reply": "Oops! I encountered a little problem. Could you try asking again?",
            "error": str(e),
        }, status=500)
        

def refund_policy(request):
    return render(request, "myApp/refund_policy.html")

def help_ai(request):
    return render(request, "Agent/help_ai.html")

def pricing(request):
    order = ['agent', 'company', 'individual']
    plans = sorted(SubscriptionPlan.objects.all(), key=lambda p: order.index(p.landlord_type))
    context = {
        'plans': plans
    }
    return render(request, 'myApp/pricing.html', context)

def tenant_profile(request):
    tenant = request.user.tenant
    context = {
        'tenant': tenant
    }
    return render(request, "myApp/tenant_profile.html", context)

@login_required
def edit_tenant_profile(request):
    tenant = request.user.tenant

    if request.method == "POST":
        form = TenantEditForm(request.POST, request.FILES, instance=tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("myApp:tenant_profile")
    else:
        form = TenantEditForm(instance=tenant, user=request.user)

    return render(request, "myApp/edit_tenant_profile.html", {"form": form})


def mover_policy(request):
    return render(request, "transporters/mover_policy.html")

def support(request):
    return render(request, "myApp/support.html")
