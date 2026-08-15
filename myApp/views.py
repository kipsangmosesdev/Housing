import json
from datetime import timedelta, timezone
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Avg
from django.http import JsonResponse
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
from .models import (GeneralTip, Payment, Property, PropertyImage, PropertyType,
                     PropertyView, SystemRating, Tenant, Transporter,
                     TransporterSubscription, adminUpdate)


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


def property_map_view(request):
    # Subquery: get latest expiry_date per landlord
    latest_payment = Payment.objects.filter(
        landlord=OuterRef('landlord'),is_successful=True
    ).order_by('-expiry_date').values('expiry_date')[:1]

    # Fetch approved properties with landlord expiry annotation
    properties = (
        Property.objects.annotate(
            landlord_expiry=Subquery(latest_payment, output_field=DateTimeField())
        )
        .filter(
            is_approved=True,
            landlord__is_verified=True,  # Only verified landlords
            )
        .select_related("landlord")
        .order_by('-date_posted')
    )

    # Filter in Python: allow paid landlords OR trial landlords
    valid_properties = [
        prop for prop in properties
        if (
            # Paid landlords: is_paid and not expired
            (prop.landlord.is_paid and prop.landlord_expiry and prop.landlord_expiry >= timezone.now())
        )
        or (
            # Trial landlords: is_free_trial and not expired
            (prop.landlord.is_free_trial and prop.landlord.trial_expiry and prop.landlord.trial_expiry >= timezone.now())
        )
    ]
    
    return render(request, 'myApp/property_map.html', {
        'properties': valid_properties,
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
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json
from geopy.distance import geodesic


# Remove the custom haversine function entirely since we're using geopy's geodesic
# which is more accurate and doesn't need manual corrections

# Nearby properties using high-precision geodesic distances
@csrf_exempt
# @login_required(login_url='unified_login')
def nearby_properties_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    # --------------------------
    # 1. Get user coordinates safely
    # --------------------------
    try:
        data = json.loads(request.body)
        user_lat = float(data.get("latitude"))
        user_lon = float(data.get("longitude"))
        user_coord = (user_lat, user_lon)
    except (TypeError, ValueError, KeyError):
        return JsonResponse({"error": "Invalid coordinates"}, status=400)

    max_distance_km = 5  # Define the maximum distance in kilometers to filter nearby properties
    now = timezone.now()
    nearby = []

    # ---------------------------------------
    # 2. Fetch approved and available properties
    # ---------------------------------------
    properties = Property.objects.select_related("landlord").filter(
        is_approved=True,
        is_available=True,
        landlord__is_verified=True,  # Only verified landlords
    )[:15]  # Limit to 15 for performance; adjust as needed

    # ---------------------------------------
    # 3. Loop through properties and calculate distances
    # ---------------------------------------
    for prop in properties:
        if prop.latitude is None or prop.longitude is None:
            continue

        property_coord = (prop.latitude, prop.longitude)

        # High-precision geodesic distance (most accurate method)
        distance = geodesic(user_coord, property_coord).km

        if distance > max_distance_km:
            continue  # out of range

        landlord = prop.landlord
        has_active_payment = Payment.objects.filter(
            landlord=landlord,
            expiry_date__gte=now
        ).exists()
        has_free_trial = (
            landlord.is_free_trial and
            landlord.trial_expiry and
            landlord.trial_expiry >= now
        )

        if not (has_active_payment or has_free_trial):
            continue

        nearby.append({
            "id": prop.id,
            "title": prop.title,
            # Get image from PropertyImage model if available, else fallback to main image_url
            "image_url": prop.images.first().image.url if prop.images.exists() else (prop.image.url if prop.image else ""),
            "property_type": prop.property_type.name if prop.property_type else "",
            "is_verified": prop.is_verified,
            "rent": prop.rent,
            "estate": prop.estate,
            "address": prop.address,
            "bedrooms": prop.bedrooms,
            "bathrooms": prop.bathrooms,
            "distance": round(distance, 2),  # Round to 2 decimal places for display
            "lat": prop.latitude,
            "lng": prop.longitude,
        })

    # Sort by closest first
    nearby.sort(key=lambda x: x["distance"])

    return JsonResponse({
        "count": len(nearby),
        "properties": nearby
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

import hashlib
import os
import random
import re
from django.core.cache import cache
from django.db.models import Q

from .models import FAQ, Property

# --- OpenAI Setup ---
try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
        OPENAI_AVAILABLE = False
    else:
        OPENAI_AVAILABLE = False
except ImportError:
    OPENAI_AVAILABLE = False
# filter properties of non expired subscription
    # Subquery to get latest expiry_date per landlord
    latest_payment = Payment.objects.filter(
        landlord=OuterRef('landlord')
    ).order_by('-expiry_date').values('expiry_date')[:1]

    # Annotate and filter properties with valid subscriptions
    properties = (
        Property.objects.annotate(
            landlord_expiry=Subquery(latest_payment, output_field=DateTimeField())
        )
        .filter(
            is_approved=True,
            landlord__is_verified=True,
            landlord__is_paid=True,
            landlord_expiry__gte=timezone.now()
        )
        .order_by('-date_posted')
    )
# --- Number word mapping for bedrooms (1–10) ---

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

def extract_bedroom_count(text, room_type="bedroom"):
    text = text.lower().strip()

    # 1 Check numeric form (e.g. 2 bedrooms)
    if match := re.search(rf"\b(\d+)\s*{room_type}s?\b", text):
        return int(match.group(1))

    # 2 Check number word form (e.g. two bedrooms)
    for word, num in NUMBER_WORDS.items():
        pattern = re.compile(rf"\b{word}\s*{room_type}s?\b", re.IGNORECASE)
        if pattern.search(text):
            return num

    return None


# --- Global amenity keywords ---
AMENITY_KEYWORDS = [
    # Structure & Finishes
    "flooring", "cement screed flooring", "vinyl flooring", "marble flooring",
    "wood floor", "natural wood flooring", "tiles", "tile floor", 
    "ceiling", "gypsum ceiling", "pop ceiling", "pvc ceiling", "wooden ceiling", 
    "acoustic ceiling", "metal ceiling", "coffered ceiling", "ceiling fan",
    "curtain rods", "fitted cabinets", "wall mirrors",
    "natural lighting", "sliding windows", "sliding doors", 
    "double glazed windows", "soundproof", "balcony", "balcony view",
    "terrace", "rooftop", "rooftop terrace", "driveway", "paved compound",
    "garden", "outdoor sitting area", "perimeter lighting",

    # Rooms & Spaces
    "storage", "storage room", "garage", "parking", "open parking", "covered parking",
    "servant quarters", "guest cloakroom", "ensuite bathroom", "shared bathroom", 
    "shared toilet", "office", "home office", "walk-in closet", 
    "wardrobe", "built-in wardrobes", "tv wall","library",

    # Bathrooms & Wellness
    "jacuzzi", "hot tub", "steam room", "bathtub", "shower cubicle", 
    "hot shower", "squat toilet", "sitting toilet", "anti-slip tiles", 
    "anti-slip tiles in wet areas", "heated water system",

    # Kitchen & Dining
    "kitchen", "open plan kitchen", "modern kitchen", "countertop kitchen", 
    "pantry", "breakfast bar", "single sink", "double sink", 
    "dishwasher", "dishwashing machine", "kitchen appliances", 
    "built-in appliances", "energy-efficient appliances", "kitchen cabinets",
    "built-in kitchen appliances", "refrigerator space", "chimney",

    # Laundry & Cleaning
    "laundry", "laundry room", "laundry drying area", "washing machine", 
    "in-unit laundry", "in-unit laundry machine", "ironing station", 
    "cleaning services",

    # Power & Utilities
    "solar", "solar panel system", "solar backup", "generator", "generator backup",
    "generator power backup", "water backup", "reliable water supply", 
    "borehole water", "rooftop water tank", "water pressure boosters",
    "greywater recycling", "greywater recycling system", 
    "rainwater harvesting", "sun-powered hot water", 
    "sun-powered hot water system", "wastewater treatment",
    "wastewater treatment system", "electricity-prepaid", 
    "electricity-postpaid", "electricity tokens",

    # Sustainability
    "recycling", "recycling center", "recycling pickup", 
    "composting facility", "energy-efficient", 

    # Entertainment & Connectivity
    "dstv", "satellite dish", "satellite dish installation ready", 
    "tv points", "wall-mounted tv", "wall-mounted tv points", 
    "cable tv", "cable tv ready", "wifi", "fiber", "fiber internet ready", 
    "internet", "smart lighting", "home automation", 
    "home automation system", "smart thermostat", "water leak sensors", 
    "smart water leak sensors", "smart home", "smart doorbell", 
    "video doorbell", "smart lock",

    # Lifestyle & Furnishings
    "furnished", "fully furnished", "outdoor grilling", "outdoor grilling spot",
    "bbq", "barbecue", "gym", "swimming pool", "pool", 
    "jogging track", "children play area", "kids play area", 
    "game room", "library", "restaurant", "daycare", "shared kitchen", 
    "study area", "shared study", "shared study area", "event space", 
    "meeting space", "shared event space", "reception desk", 
    "visitor parking", "support staff", "resident staff", 
    "resident support staff available", "pet-friendly", "pet-friendly areas",
    "elevator", "lift", "rooftop terrace", "outdoor sitting area",

    # Comfort & Climate
    "fireplace", "underfloor heating", "air conditioning", "ac", "cooling",
    "balcony view", "natural lighting", "soundproof walls", 
    "soundproof windows", "double glazed windows", "ceiling fan",

    # Security
    "smart lock", "smart doorbell", "video doorbell", "intercom", 
    "intercom system", "rfid", "keycard access", "rfid / keycard access", 
    "biometric access", "motion sensor", "motion sensor lighting",
    "security lighting", "boom gate", "double gate", "double gate system",
    "guard dogs", "guard house", "security patrols", "security guard", 
    "visitor management", "visitor management system", 
    "alarm", "security alarm", "security alarm system", 
    "cctv", "24/7 cctv", "24/7 cctv surveillance", "gated community", 
    "perimeter wall", "electric fence",

    # Fire & Safety
    "fire hose", "fire hose reels", "sprinkler system", 
    "smoke detectors", "carbon monoxide detectors", "fire extinguishers", 
    "emergency alert", "emergency alert system", "emergency stairwell",
    "fire exit", "fire exit/emergency stairwell", "assembly point", 
    "emergency assembly point",

    # Accessibility
    "disabled access", "wheelchair accessible",
]

# --- Utility: Cache Key ---
def make_cache_key(user_query, context=""):
    key_string = f"rental_tip_{user_query}_{context}"
    return hashlib.md5(key_string.encode("utf-8")).hexdigest()

# --- Friendly Greetings ---
def get_friendly_greeting():
    greetings = [
        "Hey there! 👋 I'm here to help you find your perfect rental in Kenya.",
        "Hi! 😊 Ready to find your next home? I'm here to help!",
        "Hello! 🏡 Let's find you a great place to live in Kenya!",
        "Hey! 👍 Great to see you. Let's hunt for your ideal rental together!",
        "Hi there! 🌟 I'm excited to help you find your next home!"
    ]
    return random.choice(greetings)

# --- Human-like Fallback Tips ---
def get_fallback_tip(query=""):
    general_tips = GeneralTip.objects.all().values_list('tip', flat=True)
    if not general_tips:
        return "Always visit the property in person before signing any agreements."
    return random.choice(general_tips)

# --- Rental Tip Generator with Human Touch ---
def generate_rental_tip(user_query, context=""):
    cache_key = make_cache_key(user_query, context)
    cached = cache.get(cache_key)
    if cached:
        return cached

    fallback_tip = get_fallback_tip(user_query)
    if not OPENAI_AVAILABLE:
        return f"Just a thought: {fallback_tip}"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a friendly, knowledgeable rental advisor in Kenya. Offer practical, conversational advice. Sound like a helpful human, not a robot. Keep it brief and engaging."},
                {"role": "user", "content": f"User is looking for rental advice. Query: {user_query}\nContext: {context or 'general rental search'}"}
            ],
            max_tokens=700,
            temperature=0.8
        )
        tip = response.choices[0].message.content.strip()
        cache.set(cache_key, tip, 7200)  # cache 2 hrs
        return tip
    except Exception as e:
        print(f"[OpenAI error] {e}")
        return f" {fallback_tip}"

# --- Conversation Session Store ---
conversation_sessions = {}

# --- Regex Helper ---
def extract_pattern(pattern, text, cast=int):
    match = re.search(pattern, text)
    if match:
        try:
            return cast(match.group(1))
        except Exception:
            return match.group(1)
    return None

# --- Human Response Formatter ---
def format_human_response(ai_reply, properties_data, user_message):
    """Make the AI response sound more human and engaging"""
    
    # Add natural openings based on context
    user_msg_lower = user_message.lower()
    
    if any(word in user_msg_lower for word in ["thank", "thanks", "appreciate"]):
        openings = ["You're welcome!", "Happy to help!", "Anytime!", "My pleasure!"]
    elif any(word in user_msg_lower for word in ["hi", "hello", "hey", "greetings"]):
        openings = [get_friendly_greeting()]
    else:
        openings = [
            "Sure thing!", "Got it!", "I found some options for you!", 
            "Here's what I found!", "Great question!", "I can help with that!"
        ]
    
    # Start with a natural opening
    human_reply = random.choice(openings) + " "
    
    # Add the AI reply
    human_reply += ai_reply
    
    # Add property count context naturally
    if properties_data:
        count = len(properties_data)
        if count == 1:
            property_phrases = [
                " I found 1 property you might like! 👇",
                " There's 1 option that looks perfect for you! 👇",
                " I've got 1 listing that matches what you're looking for! 👇"
            ]
        else:
            property_phrases = [
                f" I found {count} properties you might like! 👇",
                f" Here are {count} options that match what you're looking for! 👇",
                f" I've got {count} listings that could work for you! 👇"
            ]
        human_reply += random.choice(property_phrases)
    else:
        no_match_phrases = [
            " Hmm, I couldn't find exact matches with those criteria. Maybe try adjusting your budget or location?",
            " Nothing's popping up with those filters. Want to try broadening the search a bit?",
            " No perfect matches yet. Maybe tweak your requirements slightly? I'm sure we'll find something!"
        ]
        human_reply += random.choice(no_match_phrases)
    
    # Add a friendly closing
    closings = [
        " Feel free to ask me anything else!",
        " Let me know if you need more details!",
        " What else can I help you with?",
        " Need anything else? Just ask!"
    ]
    human_reply += random.choice(closings)
    
    return human_reply

# --- Main AI Agent View ---
@csrf_exempt
def ai_agent(request):
    session_id = request.COOKIES.get("sessionid", "default")

    # Initialize conversation memory
    if session_id not in conversation_sessions:
        conversation_sessions[session_id] = [
            {"role": "system", "content": (
                "You are XbomaSwift AI, a friendly and helpful rental assistant for Kenya. "
                "You speak like a knowledgeable human friend who knows about real estate. "
                "Use natural language, contractions, and occasional emojis to be engaging. "
                "Help users find apartments, houses, or rooms to rent. "
                "Be warm, personable, and offer practical advice. "
                "If no properties match, suggest adjusting filters politely and helpfully. "
                "Keep responses conversational but informative."
            )}
        ]

    if request.method == "GET":
        return JsonResponse({
            "reply": get_friendly_greeting()
        })

    if request.method != "POST":
        return JsonResponse({"error": "Oops, something went wrong! Try again."}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
        if not user_message:
            return JsonResponse({"reply": "I'd love to help! What are you looking for in a rental?"})

        # Store user message
        conversation_sessions[session_id].append({"role": "user", "content": user_message})
        if len(conversation_sessions[session_id]) > 20:
            conversation_sessions[session_id] = conversation_sessions[session_id][-20:]

        # --- Property filtering ---
        qs = Property.objects.filter(is_available=True, is_approved=True)
        # Subquery: only landlords with active subscription and on trial
        latest_payment = Payment.objects.filter(
            landlord=OuterRef("landlord"), is_successful=True
        ).order_by("-expiry_date").values("expiry_date")[:1]

        qs = qs.annotate(
            landlord_expiry=Subquery(latest_payment, output_field=DateTimeField())
        ).filter(Q(landlord__is_paid=True,landlord__is_verified=True, landlord_expiry__gte=timezone.now()) | 
        Q(landlord__is_free_trial=True,landlord__is_verified=True, landlord__trial_expiry__gte=timezone.now()))
        context_info, lower_msg = [], user_message.lower()

        # City filter
        if match := re.search(r"(nairobi|nakuru|kisumu|mombasa|eldoret)", lower_msg):
            qs = qs.filter(city__icontains=match.group(1))
            context_info.append(f"city: {match.group(1)}")
    
        # --- Property Type Filter (Keep regex + dictionary enhancement) ---
        PROPERTY_TYPE_SYNONYMS = {
            "apartment": [
                "flat", "flats", "apartment", "apartments", "rental apartment",
                "apartment house", "block", "rental flat", "unit", "apartment unit",
                "bedsitter apartment", "studio apartment"
            ],

            "townhouse": [
                "town house", "town-home", "town home", "row house", "terraced house",
                "terrace home", "townhomes", "townhouses", "duplex", "duplex house",
                "mews", "linked house"
            ],

            "villa": [
                "maisonette", "villas", "villa house", "luxury house", "holiday home",
                "standalone house", "executive villa", "private villa", "detached house",
                "family villa"
            ],

            "bungalow": [
                "bungalows", "bungalow house", "one-storey house", "single storey",
                "ground floor house"
            ],

            "hostel": [
                "hostels", "student hostel", "student housing", "campus hostel",
                "university hostel", "college hostel", "boarding house", "dorm",
                "dormitory", "student residence"
            ],

            "condo": [
                "condominium", "condominiums", "condos","condo unit", 
                "serviced apartment", "furnished condo", "executive condo"
            ],

            "single room": [
                "single", "one room", "single bedsitter",
                "small room", "single house", "1 room", "room to let", "room for rent",
                "rental room", "simple room"
            ],

            "double room": [
                "two room", "2 room", "double", "double rooms", "double bedsitter",
                "two-bedroom bedsitter", "spacious room", "big room"
            ],

            "bedsitter": [
                "bed sitter", "bed-sitter", "studio", "studio room", "studio flat",
                "studio bedsitter", "open plan room", "self-contained room",
                "self contained", "bedsit", "bedsitters", "bachelor pad"
            ],
        }

        # 1 First, normalize using the dictionary
        for canonical_type, synonyms in PROPERTY_TYPE_SYNONYMS.items():
            for synonym in synonyms:
                if re.search(rf"\b{synonym}\b", lower_msg):
                    qs = qs.filter(property_type__name__icontains=canonical_type)
                    context_info.append(f"type: {canonical_type}")
                    break
            else:
                continue
            break

        # 2 Then, fallback to your original regex if no synonym matched
        if not any("type:" in info for info in context_info):
            if match := re.search(
                r"(villa|maisonette|apartment|cottage|townhouse|bungalow|hostel|condo|single room|double room|bedsitter|bed sitter)",
                lower_msg
            ):
                qs = qs.filter(property_type__name__icontains=match.group(1))
                context_info.append(f"type: {match.group(1)}")
           
        # --- Estate filter (dynamic) ---
        estates = Property.objects.values_list("estate", flat=True).distinct()
        for est in estates:
            if est and est.lower() in lower_msg:
                qs = qs.filter(estate__icontains=est)
                context_info.append(f"estate: {est}")
                break
        
        # --- Bathrooms filter (dynamic) ---
        bathroom_numbers = Property.objects.values_list("bathrooms", flat=True).distinct()
        for num in bathroom_numbers:
            if num and str(num) in lower_msg:
                qs = qs.filter(bathrooms=num)
                context_info.append(f"bathrooms: {num}")
                break

        # --- Bedrooms filter (dynamic) ---
        bedroom_numbers = Property.objects.values_list("bedrooms", flat=True).distinct()
        for num in bedroom_numbers:
            if num and str(num) in lower_msg:
                qs = qs.filter(bedrooms=num)
                context_info.append(f"bedrooms: {num}")
                break
        
        # --- Bedrooms filter (dynamic) ---
        bedroom_words = {
            "bedsitter": 0,
            "single room": 0,
            "studio": 0,
            "one bedroom": 1,
            "1 bedroom": 1,
            "two bedroom": 2,
            "2 bedroom": 2,
            "three bedroom": 3,
            "3 bedroom": 3,
            "four bedroom": 4,
            "4 bedroom": 4,
            "five bedroom": 5,
            "5 bedroom": 5,
        }

        bedroom_numbers = Property.objects.values_list("bedrooms", flat=True).distinct()
        found = False
        for num in bedroom_numbers:
            if num and str(num) in lower_msg:
                qs = qs.filter(bedrooms=num)
                context_info.append(f"bedrooms: {num}")
                found = True
                break

        if not found:
            for phrase, num in bedroom_words.items():
                if phrase in lower_msg:
                    qs = qs.filter(bedrooms=num)
                    context_info.append(f"bedrooms: {num}")
                    break

        # --- Helper: normalize shorthand numbers like "20k" -> 20000 ---
        def normalize_number(text):
            if not text:
                return None
            text = text.lower().replace(",", "").strip()
            multiplier = 1
            if text.endswith("k"):
                multiplier = 1000
                text = text[:-1]
            try:
                return int(text) * multiplier
            except ValueError:
                return None

        # --- Rent filter ---

        # 1) Between X and Y
        match = re.search(
            r"(?:ksh\.?|kes)?\s*(\d+[kK]?)\s*(?:-|to|and|between)\s*(?:ksh\.?|kes)?\s*(\d+[kK]?)",
            lower_msg
        )
        if match:
            min_rent = normalize_number(match.group(1))
            max_rent = normalize_number(match.group(2))
            if min_rent and max_rent:
                qs = qs.filter(rent__gte=min_rent, rent__lte=max_rent)
                context_info.append(f"rent between {min_rent} and {max_rent}")

        # 2) Below X
        elif match := re.search(
            r"(?:below|under|less than|not more than)\s*(?:ksh\.?|kes)?\s*(\d+[kK]?)|(?:ksh\.?|kes)\s*(?:below|under|less than|not more than)\s*(\d+[kK]?)",
            lower_msg
        ):
            number = match.group(1) or match.group(2)
            max_rent = normalize_number(number)
            if max_rent:
                qs = qs.filter(rent__lte=max_rent)
                context_info.append(f"rent <= {max_rent}")

        # 3) Above X
        elif match := re.search(
            r"(?:above|over|greater than|from)\s*(?:ksh\.?|kes)?\s*(\d+[kK]?)|(?:ksh\.?|kes)\s*(?:above|over|greater than|from)\s*(\d+[kK]?)",
            lower_msg
        ):
            number = match.group(1) or match.group(2)
            min_rent = normalize_number(number)
            if min_rent:
                qs = qs.filter(rent__gte=min_rent)
                context_info.append(f"rent >= {min_rent}")

        # 4) Exactly or Around X
        elif match := re.search(
            r"(?:exactly|around|about|near|close to)\s*(?:ksh\.?|kes)?\s*(\d+[kK]?)|(?:ksh\.?|kes)\s*(?:exactly|around|about|near|close to)\s*(\d+[kK]?)",
            lower_msg
        ):
            number = match.group(1) or match.group(2)
            target_rent = normalize_number(number)
            if target_rent:
                # ±15% flexibility around the target value
                lower_bound = int(target_rent * 0.85)
                upper_bound = int(target_rent * 1.15)
                qs = qs.filter(rent__gte=lower_bound, rent__lte=upper_bound)
                context_info.append(f"rent ≈ {target_rent} (±15%)")


        # Balcony or balconies
        if "balcony" in lower_msg or "balconies" in lower_msg:
            qs = qs.filter(has_balcony=True)
            context_info.append("has balcony")
        
        # Verified property
        if "verified" in lower_msg:
            qs = qs.filter(is_verified=True)
            context_info.append("is verified")
        
        #featured property
        if "featured" in lower_msg:
            qs = qs.filter(featured=True)
            context_info.append("featured")

        # Amenities
        amenities = [a for a in AMENITY_KEYWORDS if a in lower_msg]
        for amenity in amenities:
            qs = qs.filter(amenities__name__icontains=amenity)
        if amenities:
            context_info.append(f"amenities: {', '.join(amenities)}")

        # --- AI or fallback ---
        cache_key = make_cache_key(user_message, ", ".join(context_info))
        ai_reply = cache.get(cache_key)

        if not ai_reply:
            try:
                # --- Offline AI Logic (Option 1 implementation) ---
                faq = FAQ.objects.filter(question__icontains=user_message).first()
                if faq:
                    ai_reply = f"I know about that! {faq.answer}"
                else:
                    # Simple offline reasoning engine
                    lower_msg = user_message.lower()

                    if "rent" in lower_msg or "price" in lower_msg:
                        ai_reply = "In Kenya, rent varies by location, urban areas like Nairobi are higher, while towns like Nakuru or Eldoret offer affordable options."
                    elif "apartment" in lower_msg or "bedsitter" in lower_msg:
                        ai_reply = "Apartments and bedsitters are great for convenience. Remember to check for water, security, and proximity to transport."
                    elif "investment" in lower_msg or "buy" in lower_msg:
                        ai_reply = "Real estate is a long-term investment. Look for growing neighborhoods and steady rental demand."
                    elif "verified" in lower_msg:
                        ai_reply = "Verified properties offer more security and assurance. Always look for the verification badge."
                    elif "featured" in lower_msg:
                        ai_reply = "Featured properties are handpicked for quality. They often have better amenities and locations."
                    else:
                        # Generic friendly fallback
                        ai_reply = f"Here's what I think. {generate_rental_tip(user_message, ', '.join(context_info))}"

            except Exception:
                faq = FAQ.objects.filter(question__icontains=user_message).first()
                if faq:
                    ai_reply = f"I know about that! {faq.answer}"
                else:
                    ai_reply = f"Here's what I think. {generate_rental_tip(user_message, ', '.join(context_info))}"

            cache.set(cache_key, ai_reply, 7200)

        conversation_sessions[session_id].append({"role": "assistant", "content": ai_reply})

        # --- Property results ---
        qs = qs.only("id", "title", "rent", "city", "estate", "bedrooms", "bathrooms", "has_balcony") \
               .prefetch_related("amenities", "images")

        properties_data = [{
            "id": p.id,
            "title": p.title,
            "rent": p.rent,
            "city": p.city,
            "estate": p.estate,
            "bedrooms": p.bedrooms,
            "bathrooms": p.bathrooms,
            "has_balcony": p.has_balcony,
            "amenities": [a.name for a in p.amenities.all()[:5]],
            "image_url": p.images.first().image.url if p.images.exists() else "",
            "images": [img.image.url for img in p.images.all()]
        } for p in qs[:10]]  # limit to 10 results

        # Format the response to sound more human
        human_reply = format_human_response(ai_reply, properties_data, user_message)

        return JsonResponse({
            "reply": human_reply,
            "properties": properties_data,
            "tip": generate_rental_tip(user_message, ", ".join(context_info))
        })

    except Exception as e:
        return JsonResponse({
            "reply": "Oops! I encountered a little problem. Could you try asking again?",
            "error": str(e)
            
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